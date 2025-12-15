import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import google.generativeai as genai
import datetime

# --- ページ設定 ---
st.set_page_config(
    page_title="将来家計シミュレーション",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- パスワード認証機能 ---
def check_password():
    """パスワード認証を行う関数"""
    # secretsにパスワードが設定されていない場合は認証をスキップ（ローカル開発用など）
    if "password" not in st.secrets:
        return True

    def password_entered():
        """パスワード入力時のチェック"""
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # パスワードをセッションから削除
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # 初回アクセス時: パスワード入力フォームを表示
        st.text_input(
            "パスワードを入力してください", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # パスワード間違い時
        st.text_input(
            "パスワードを入力してください", type="password", on_change=password_entered, key="password"
        )
        st.error("パスワードが間違っています")
        return False
    else:
        # 認証成功時
        return True

# 認証チェック実行
if not check_password():
    st.stop()  # 認証失敗または未入力時はここで処理を止める

# --- 以下、メインアプリケーション ---

# --- 定数・シナリオデータ定義 ---
# 年齢ごとの教育費 (単位: 万円)
EDUCATION_COSTS = {
    '【A】公立中心コース': [18, 18, 18, 28, 28, 28, 40, 40, 40, 40, 40, 40, 60, 60, 60, 55, 55, 55, 80, 80, 80, 80, 0],
    '【B】私立文系コース': [35, 35, 35, 175, 175, 175, 175, 175, 175, 175, 150, 150, 150, 110, 110, 110, 130, 105, 105, 105, 105, 105, 0],
    '【C】私立理系コース': [35, 35, 35, 175, 175, 175, 175, 175, 175, 175, 150, 150, 150, 110, 110, 110, 165, 140, 140, 140, 140, 140, 0],
    '【D】インター(文系大)': [35, 35, 35, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 130, 105, 105, 105, 105, 105, 0],
    '【E】インター(理系大)': [35, 35, 35, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 250, 165, 140, 140, 140, 140, 140, 0],
    '【F】支援策適用(公立)': [10, 10, 10, 10, 10, 10, 40, 40, 40, 40, 40, 40, 60, 60, 60, 48, 48, 48, 80, 80, 80, 80, 0],
    '【G】支援策適用(私立)': [10, 10, 10, 10, 10, 10, 40, 40, 40, 40, 40, 40, 150, 150, 150, 57, 57, 57, 130, 105, 105, 105, 0],
}

# 年齢ごとの養育費 (単位: 万円)
REARING_COSTS = {
    '【A】標準プラン': [85, 85, 85, 95, 95, 95, 100, 100, 100, 100, 100, 100, 110, 110, 110, 120, 120, 120, 125, 125, 125, 125, 0],
    '【B】充実プラン': [105, 105, 105, 115, 115, 115, 130, 130, 130, 130, 130, 130, 140, 140, 140, 150, 150, 150, 155, 155, 155, 155, 0],
}

# 収入プリセット
INCOME_PRESETS = {
    '【A】保守的': {'base': 800, 'growth': 1.0},
    '【B】標準': {'base': 800, 'growth': 2.0},
    '【C】積極': {'base': 800, 'growth': 3.5},
}

# 生活費プリセット
LIVING_PRESETS = {
    '【A】節約': 450,
    '【B】標準': 500,
    '【C】ゆとり': 550,
}

# 物価上昇率プリセット
INFLATION_PRESETS = {
    '0% (ゼロ)': 0.00,
    '1% (低め)': 0.01,
    '2% (標準)': 0.02,
    '3% (高め)': 0.03,
}

# 金利シナリオ
MORTGAGE_RATE_SCENARIOS = {
    '固定 (変動なし)': 'fixed',
    '安定 (±微減)': 'stable',
    '緩やか上昇 (+0.05%/年)': 'rising',
    '急上昇 (+0.2%/年)': 'sharp_rising'
}

# --- 関数定義 ---

def get_rate_fluctuation(scenario, current_base_rate):
    """金利変動シナリオに基づく翌年の金利を計算"""
    if scenario == 'fixed':
        return current_base_rate
    elif scenario == 'stable':
        return current_base_rate + (np.random.random() - 0.45) * 0.05 # 微減傾向のランダム
    elif scenario == 'rising':
        return current_base_rate + 0.05
    elif scenario == 'sharp_rising':
        return current_base_rate + 0.20
    return current_base_rate

# --- サイドバー設定 ---
st.sidebar.title("🛠️ シミュレーション設定")

# 1. お子様の設定
st.sidebar.header("👶 お子様の設定")
col1, col2 = st.sidebar.columns(2)
with col1:
    c1_year = st.number_input("第1子 誕生年", value=2025, step=1)
with col2:
    c1_month = st.number_input("第1子 誕生月", value=2, min_value=1, max_value=12)

c1_edu = st.sidebar.selectbox("第1子 教育プラン", list(EDUCATION_COSTS.keys()), index=2)
c1_rear = st.sidebar.selectbox("第1子 養育プラン", list(REARING_COSTS.keys()), index=1)

st.sidebar.markdown("---")
has_child2 = st.sidebar.checkbox("第2子を含める", value=False)
if has_child2:
    col3, col4 = st.sidebar.columns(2)
    with col3:
        c2_year = st.number_input("第2子 誕生年", value=2028, step=1)
    with col4:
        c2_month = st.number_input("第2子 誕生月", value=4, min_value=1, max_value=12)
    
    c2_edu = st.sidebar.selectbox("第2子 教育プラン", list(EDUCATION_COSTS.keys()), index=0)
    c2_rear = st.sidebar.selectbox("第2子 養育プラン", list(REARING_COSTS.keys()), index=0)
else:
    c2_year, c2_month = None, None
    c2_edu, c2_rear = None, None

# 2. 資産・iDeCo
st.sidebar.header("💰 資産・iDeCo")
initial_cash = st.sidebar.number_input("現在の貯金 (万円)", value=380, step=10)
initial_invest = st.sidebar.number_input("現在の投資 (万円)", value=1820, step=10)
invest_yield = st.sidebar.number_input("投資 年間利回り (%)", value=3.0, step=0.1)

st.sidebar.markdown("---")
initial_ideco = st.sidebar.number_input("iDeCo残高 (万円)", value=140, step=10)
ideco_monthly = st.sidebar.number_input("iDeCo 毎月掛金 (万円)", value=3.0, step=0.1)
ideco_yield = st.sidebar.number_input("iDeCo 年間利回り (%)", value=3.0, step=0.1)

# 3. 収入・生活費
st.sidebar.header("👛 収入・生活費")
income_preset_key = st.sidebar.selectbox("世帯主収入プリセット", list(INCOME_PRESETS.keys()), index=1)
income_preset = INCOME_PRESETS[income_preset_key]

head_income_base = st.sidebar.number_input("世帯主 現在年収 (万円)", value=income_preset['base'], step=10)
head_income_growth = st.sidebar.number_input("世帯主 昇給率 (%/年)", value=income_preset['growth'], step=0.1)
partner_income = st.sidebar.number_input("パートナー年収 (万円)", value=0, step=10)

st.sidebar.markdown("---")
living_preset_key = st.sidebar.selectbox("生活費プリセット", list(LIVING_PRESETS.keys()), index=1)
living_cost_base = st.sidebar.number_input("年間生活費 (万円)", value=LIVING_PRESETS[living_preset_key], step=10)

inflation_key = st.sidebar.selectbox("物価上昇率", list(INFLATION_PRESETS.keys()), index=2)
inflation_rate = INFLATION_PRESETS[inflation_key]

# 4. 住宅ローン
st.sidebar.header("🏠 住宅ローン")
mortgage_principal = st.sidebar.number_input("借入金額 (万円)", value=6460, step=100)
col_m1, col_m2 = st.sidebar.columns(2)
with col_m1:
    mortgage_start_year = st.number_input("返済開始年", value=2024)
with col_m2:
    mortgage_end_year = st.number_input("完済予定年", value=2059)

mortgage_base_rate = st.sidebar.number_input("基準金利 (%)", value=2.841, step=0.001, format="%.3f")
mortgage_reduction_rate = st.sidebar.number_input("引下幅 (%)", value=2.057, step=0.001, format="%.3f")
mortgage_rate_scenario_key = st.sidebar.selectbox("金利変動シナリオ", list(MORTGAGE_RATE_SCENARIOS.keys()))
mortgage_rate_scenario = MORTGAGE_RATE_SCENARIOS[mortgage_rate_scenario_key]

# --- シミュレーション実行ロジック ---

# シミュレーション期間の設定
start_year = 2025
current_year = datetime.datetime.now().year
last_child_grad_year = c1_year + 23
if has_child2:
    last_child_grad_year = max(last_child_grad_year, c2_year + 23)

end_year = max(start_year + 30, last_child_grad_year) # 少なくとも30年、または末子卒業まで
years = list(range(start_year, end_year + 1))

# データフレームの準備
df = pd.DataFrame(index=years)
df['西暦'] = df.index
df['経過年数'] = df['西暦'] - start_year

# 年齢計算
df['第1子年齢'] = df['西暦'] - c1_year
if has_child2:
    df['第2子年齢'] = df['西暦'] - c2_year
else:
    df['第2子年齢'] = np.nan

# 収入計算
df['世帯主収入'] = head_income_base * (1 + head_income_growth / 100) ** df['経過年数']
df['世帯収入'] = df['世帯主収入'] + partner_income

# 教育費・養育費計算
def get_cost(age, cost_list):
    if 0 <= age < len(cost_list):
        return cost_list[age]
    return 0

# シナリオデータの編集機能 (Data Editor)
st.title("将来家計シミュレーション 📊")

with st.expander("教育費・養育費データの編集 (詳細設定)", expanded=False):
    # 辞書をDataFrameに変換して編集可能にする
    df_edu = pd.DataFrame(EDUCATION_COSTS).T
    df_edu.columns = [f"{i}歳" for i in range(23)]
    edited_edu = st.data_editor(df_edu, use_container_width=True)
    
    df_rear = pd.DataFrame(REARING_COSTS).T
    df_rear.columns = [f"{i}歳" for i in range(23)]
    edited_rear = st.data_editor(df_rear, use_container_width=True)

# 編集後のデータを使用してコスト計算
df['第1子教育費'] = df['第1子年齢'].apply(lambda x: get_cost(x, edited_edu.loc[c1_edu].tolist()) if x >= 0 else 0)
df['第1子養育費'] = df['第1子年齢'].apply(lambda x: get_cost(x, edited_rear.loc[c1_rear].tolist()) if x >= 0 else 0)

if has_child2:
    df['第2子教育費'] = df['第2子年齢'].apply(lambda x: get_cost(x, edited_edu.loc[c2_edu].tolist()) if x >= 0 else 0)
    df['第2子養育費'] = df['第2子年齢'].apply(lambda x: get_cost(x, edited_rear.loc[c2_rear].tolist()) if x >= 0 else 0)
else:
    df['第2子教育費'] = 0
    df['第2子養育費'] = 0

df['教育費合計'] = df['第1子教育費'] + df['第2子教育費']
df['養育費合計'] = df['第1子養育費'] + df['第2子養育費']
df['教育・養育費小計'] = df['教育費合計'] + df['養育費合計']

# 生活費 (インフレ考慮)
df['生活費'] = living_cost_base * (1 + inflation_rate) ** df['経過年数']

# 住宅ローン計算 (年次進行)
df['基準金利'] = mortgage_base_rate
# 金利変動シミュレーション
current_base_rate = mortgage_base_rate
rate_history = []
for _ in years:
    if len(rate_history) > 0: # 初年度以降
        current_base_rate = get_rate_fluctuation(mortgage_rate_scenario, current_base_rate)
    rate_history.append(current_base_rate)
df['基準金利'] = rate_history
df['適用金利'] = (df['基準金利'] - mortgage_reduction_rate).clip(lower=0) # マイナス金利防止

# ローン残高・返済額の推移計算
loan_balances = []
loan_payments = []
current_loan_balance = mortgage_principal * 10000 # 円単位
remaining_loan_years = mortgage_end_year - mortgage_start_year

# シミュレーション開始前までの経過期間を計算
months_before_sim = max(0, (start_year - mortgage_start_year) * 12 + (4 - 1)) # 2025年4月基準

# 開始前までの残高減少を簡易計算 (初年度金利で計算)
initial_monthly_rate = (mortgage_base_rate - mortgage_reduction_rate) / 100 / 12
initial_monthly_payment = 0
if remaining_loan_years > 0:
    if initial_monthly_rate > 0:
         initial_monthly_payment = (current_loan_balance * initial_monthly_rate * (1 + initial_monthly_rate)**(remaining_loan_years*12)) / ((1 + initial_monthly_rate)**(remaining_loan_years*12) - 1)
    else:
         initial_monthly_payment = current_loan_balance / (remaining_loan_years*12)

# シミュレーション開始時点の残高を推計
for _ in range(months_before_sim):
    if current_loan_balance > 0:
        interest = current_loan_balance * initial_monthly_rate
        principal_paid = initial_monthly_payment - interest
        current_loan_balance -= principal_paid
current_loan_balance = max(0, current_loan_balance)

# 年次ループ計算
current_cash = initial_cash * 10000
current_invest = initial_invest * 10000
current_ideco = initial_ideco * 10000

asset_history = []
invest_history = []
cash_history = []
ideco_history = []
bankrupt_year = None

for i, year in enumerate(years):
    # --- ローン ---
    # 毎年、残り期間と現在金利で返済額を再計算 (簡易変動金利モデル)
    years_left = max(0, mortgage_end_year - year)
    months_left = years_left * 12
    annual_payment = 0
    
    if current_loan_balance > 0 and months_left > 0:
        monthly_r = df['適用金利'].iloc[i] / 100 / 12
        if monthly_r > 0:
            monthly_p = (current_loan_balance * monthly_r * (1 + monthly_r)**months_left) / ((1 + monthly_r)**months_left - 1)
        else:
            monthly_p = current_loan_balance / months_left
            
        # 1年分 (12ヶ月) の返済
        for _ in range(12):
            if current_loan_balance <= 0: break
            interest = current_loan_balance * monthly_r
            principal_p = monthly_p - interest
            current_loan_balance -= principal_p
            annual_payment += monthly_p
    
    current_loan_balance = max(0, current_loan_balance)
    loan_balances.append(current_loan_balance / 10000) # 万円
    loan_payments.append(annual_payment / 10000) # 万円

    # --- 資産運用 ---
    # 投資リターン
    invest_ret = current_invest * (invest_yield / 100)
    current_invest += invest_ret
    
    # iDeCoリターン + 拠出
    ideco_contribution = ideco_monthly * 10000 * 12
    ideco_ret = (current_ideco + ideco_contribution) * (ideco_yield / 100) # 簡易的に期初+拠出分に利回り適用
    current_ideco += ideco_contribution + ideco_ret

    # --- 収支 ---
    income_val = df['世帯収入'].iloc[i] * 10000
    spending_val = (df['教育費合計'].iloc[i] + df['養育費合計'].iloc[i] + df['生活費'].iloc[i]) * 10000 + annual_payment
    
    # iDeCo拠出は手取り収入から引く支出扱いではなく、資産移転だが、
    # ここではキャッシュフロー計算上、手元現金から出ていくものとして扱う
    cash_flow = income_val - spending_val - ideco_contribution
    
    current_cash += cash_flow
    
    # --- 資産取り崩しロジック ---
    if current_cash < 0:
        shortfall = -current_cash
        if current_invest >= shortfall:
            current_invest -= shortfall
            current_cash = 0
        else:
            # 投資でも足りない -> 破綻 (貯金マイナス)
            current_cash += current_invest # 全額充当
            current_invest = 0
            if bankrupt_year is None:
                bankrupt_year = year

    cash_history.append(current_cash / 10000)
    invest_history.append(current_invest / 10000)
    ideco_history.append(current_ideco / 10000)
    asset_history.append((current_cash + current_invest + current_ideco) / 10000)


df['ローン返済'] = loan_payments
df['ローン残高'] = loan_balances
df['貯金'] = cash_history
df['投資'] = invest_history
df['iDeCo'] = ideco_history
df['総資産'] = df['貯金'] + df['投資'] + df['iDeCo']
df['貯金+投資'] = df['貯金'] + df['投資']
df['収支'] = df['世帯収入'] - (df['教育・養育費小計'] + df['生活費'] + df['ローン返済']) # iDeCo拠出は除く(貯蓄性のため)

# --- 結果表示 ---

# アラート表示
if bankrupt_year:
    st.error(f"⚠️ **家計破綻の警告**: {bankrupt_year}年（第1子 {bankrupt_year - c1_year}歳）に資金（貯金＋投資）が底をつきます。")

# サマリーカード
col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    total_edu_rear = df['教育・養育費小計'].sum()
    st.metric("教育・養育費総額", f"{total_edu_rear:,.0f} 万円", f"教育: {df['教育費合計'].sum():,.0f} / 養育: {df['養育費合計'].sum():,.0f}")

with col_s2:
    min_asset = df['総資産'].min()
    min_asset_year = df.loc[df['総資産'].idxmin(), '西暦']
    st.metric("最も資産が減る時期", f"{min_asset_year}年", f"残高: {min_asset:,.0f} 万円")

with col_s3:
    final_val = df.iloc[-1]
    final_net_asset = final_val['総資産'] - final_val['ローン残高']
    st.metric("最終時点の純資産", f"{final_net_asset:,.0f} 万円", f"総資産: {final_val['総資産']:,.0f} - ローン: {final_val['ローン残高']:,.0f}")

# グラフ
st.subheader("📊 資産状況の推移")

# 表示項目の選択
show_options = st.multiselect(
    "グラフに表示する項目を選択:",
    ['総資産', 'ローン残高', '貯金+投資', 'iDeCo'],
    default=['総資産', 'ローン残高']
)

fig = go.Figure()

if '総資産' in show_options:
    fig.add_trace(go.Scatter(x=df['西暦'], y=df['総資産'], mode='lines', name='総資産', line=dict(color='#4f46e5', width=3)))
if 'ローン残高' in show_options:
    fig.add_trace(go.Scatter(x=df['西暦'], y=df['ローン残高'], mode='lines', name='ローン残高', line=dict(color='#ef4444', dash='dot')))
if '貯金+投資' in show_options:
    fig.add_trace(go.Scatter(x=df['西暦'], y=df['貯金+投資'], mode='lines', name='貯金+投資', line=dict(color='#10b981')))
if 'iDeCo' in show_options:
    fig.add_trace(go.Scatter(x=df['西暦'], y=df['iDeCo'], mode='lines', name='iDeCo', line=dict(color='#f59e0b')))

fig.update_layout(
    xaxis_title="西暦",
    yaxis_title="金額 (万円)",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)

# 詳細データテーブル
st.subheader("📋 年次詳細データ")
display_cols = ['西暦', '第1子年齢', '第2子年齢', '世帯収入', '教育費合計', '養育費合計', '生活費', 'ローン返済', '収支', '総資産', 'ローン残高']
st.dataframe(df[display_cols].style.format("{:,.0f}"), use_container_width=True)

# AI診断エリア
st.subheader("🤖 AI家計診断")
user_api_key = st.text_input("Gemini APIキーを入力してください (診断機能を使用する場合)", type="password")

if st.button("AIに診断してもらう"):
    if not user_api_key:
        st.warning("APIキーを入力してください。")
    else:
        try:
            # API設定
            genai.configure(api_key=user_api_key)
            
            # 【重要】ユーザーの利用可能リストにあった有効なモデル名を指定
            # あなたのリストに 'models/gemini-2.0-flash' があるためこれを使います
            model_name = 'gemini-2.0-flash'
            model = genai.GenerativeModel(model_name)
            
            prompt = f"""
            あなたはプロのファイナンシャルプランナーです。以下のシミュレーション結果に基づき、辛口かつ具体的なアドバイスを日本語で作成してください。

            # シミュレーション条件
            - 第1子: {c1_year}年生まれ ({c1_edu})
            - 第2子: {c2_year}年生まれ ({c2_edu})
            - 収入シナリオ: {income_preset_key} (世帯主現在 {head_income_base}万円)
            - 初期資産: 貯金{initial_cash}万, 投資{initial_invest}万, iDeCo{initial_ideco}万

            # 結果概要
            - 最終純資産(シミュレーション終了時): {final_net_asset:,.0f}万円
            - 最も資産が減る時期: {min_asset_year}年 (残高 {min_asset:,.0f}万円)
            - 破綻の有無: {'あり ('+str(bankrupt_year)+'年)' if bankrupt_year else 'なし'}

            # アドバイスの構成
            1. 家計の安全性診断 (A~E評価)
            2. 資金繰りの危険な時期とその対策
            3. 老後資金の見通し
            4. 投資・iDeCo活用の評価
            """
            
            with st.spinner(f"AI ({model_name}) が分析中..."):
                response = model.generate_content(prompt)
                st.markdown(response.text)
                
        except Exception as e:
            st.error("エラーが発生しました。以下を確認してください。")
            st.code(str(e))
            
            # 診断用: 実際に利用可能なモデル一覧を取得・表示する
            st.info("💡 ヒント: あなたのAPIキーで利用可能なモデル一覧を調査します...")
            try:
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
                
                if available_models:
                    st.write("**現在利用可能なモデル名:**")
                    st.code("\n".join(available_models))
                    st.write("もしエラーが続く場合は、上記リストにある名前をコード内の 'model_name' にコピーして修正してください。")
                else:
                    st.warning("利用可能なモデルが見つかりませんでした。APIキーが正しいか確認してください。")
            except Exception as e2:
                st.error(f"モデル一覧の取得にも失敗しました: {e2}")
