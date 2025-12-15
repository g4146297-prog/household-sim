import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import google.generativeai as genai
import datetime

# --- ページ設定 ---
st.set_page_config(
    page_title="将来家計シミュレーション (修正版)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- パスワード認証機能 ---
def check_password():
    """パスワード認証を行う関数"""
    if "password" not in st.secrets:
        return True

    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("パスワードが間違っています")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- 定数・シナリオデータ定義 (東京都市部・2025年版) ---
EDUCATION_COSTS = {
    '【A】公立中心(塾しっかり)': [10, 10, 10, 25, 25, 25, 35, 35, 35, 40, 45, 50, 60, 60, 80, 60, 70, 90, 90, 55, 55, 55, 0],
    '【B】中高公立・私大文系': [10, 10, 10, 25, 25, 25, 35, 35, 35, 40, 45, 50, 60, 60, 80, 60, 70, 90, 135, 105, 105, 105, 0],
    '【C】中高公立・私大理系': [10, 10, 10, 25, 25, 25, 35, 35, 35, 40, 45, 50, 60, 60, 80, 60, 70, 90, 170, 150, 150, 150, 0],
    '【D】高校から私立(文系大)': [10, 10, 10, 25, 25, 25, 35, 35, 35, 40, 45, 50, 60, 60, 80, 100, 100, 110, 135, 105, 105, 105, 0],
    '【E】高校から私立(理系大)': [10, 10, 10, 25, 25, 25, 35, 35, 35, 40, 45, 50, 60, 60, 80, 100, 100, 110, 170, 150, 150, 150, 0],
    '【F】中学受験(私立中高一貫)・文系大': [10, 10, 10, 25, 25, 25, 35, 35, 35, 80, 100, 140, 145, 145, 150, 110, 110, 120, 135, 105, 105, 105, 0],
    '【G】中学受験(私立中高一貫)・理系大': [10, 10, 10, 25, 25, 25, 35, 35, 35, 80, 100, 140, 145, 145, 150, 110, 110, 120, 170, 150, 150, 150, 0],
    '【H】小学校から私立(文系大)': [10, 10, 10, 25, 25, 25, 160, 160, 160, 160, 170, 180, 145, 145, 150, 110, 110, 120, 135, 105, 105, 105, 0],
    '【I】小学校から私立(理系大)': [10, 10, 10, 25, 25, 25, 160, 160, 160, 160, 170, 180, 145, 145, 150, 110, 110, 120, 170, 150, 150, 150, 0],
}

REARING_COSTS = {
    '【A】標準プラン': [80, 80, 80, 90, 90, 90, 100, 100, 100, 110, 110, 120, 130, 130, 130, 140, 140, 140, 100, 100, 100, 100, 0],
    '【B】ゆとりプラン': [100, 100, 100, 110, 110, 110, 120, 120, 120, 130, 130, 140, 150, 150, 150, 160, 160, 160, 150, 150, 150, 150, 0],
}

INCOME_PRESETS = {
    '【A】保守的': {'base': 800, 'growth': 0.5},
    '【B】標準': {'base': 800, 'growth': 1.5},
    '【C】積極': {'base': 800, 'growth': 3.0},
}

LIVING_PRESETS = {
    '【A】節約 (月30万)': 360,
    '【B】標準 (月38万)': 456, 
    '【C】ゆとり (月48万)': 576,
}

INFLATION_PRESETS = {'0% (ゼロ)': 0.00, '1% (低め)': 0.01, '2% (標準)': 0.02, '3% (高め)': 0.03}
MORTGAGE_RATE_SCENARIOS = {'固定 (変動なし)': 'fixed', '安定 (±微減)': 'stable', '緩やか上昇 (+0.05%/年)': 'rising', '急上昇 (+0.2%/年)': 'sharp_rising'}

# --- 関数定義 ---
def get_rate_fluctuation(scenario, current_base_rate):
    if scenario == 'fixed': return current_base_rate
    elif scenario == 'stable': return current_base_rate + (np.random.random() - 0.45) * 0.05
    elif scenario == 'rising': return current_base_rate + 0.05
    elif scenario == 'sharp_rising': return current_base_rate + 0.20
    return current_base_rate

def get_cost(age, cost_list):
    if 0 <= age < len(cost_list): return cost_list[age]
    return 0

def get_boarding_cost(age, is_boarding, cost_per_year):
    if is_boarding and (18 <= age <= 21): return cost_per_year
    return 0

# --- サイドバー設定 ---
st.sidebar.title("🛠️ 設定")

# 1. 基本情報
st.sidebar.header("👤 基本情報・収入")
head_age = st.sidebar.number_input("世帯主 現在年齢 (歳)", value=35, step=1, help="iDeCoの積立終了時期(60歳)の判定に使用します")
income_preset_key = st.sidebar.selectbox("世帯主収入シナリオ", list(INCOME_PRESETS.keys()), index=1)
income_preset = INCOME_PRESETS[income_preset_key]
head_income_base = st.sidebar.number_input("世帯主 現在年収 (万円)", value=income_preset['base'], step=10)
head_income_growth = st.sidebar.number_input("世帯主 昇給率 (%/年)", value=income_preset['growth'], step=0.1)
partner_income = st.sidebar.number_input("パートナー年収 (万円)", value=0, step=10)

# 2. 資産・iDeCo
st.sidebar.header("💰 資産・iDeCo")
initial_cash = st.sidebar.number_input("現在の貯金 (万円)", value=380, step=10)
initial_invest = st.sidebar.number_input("現在の投資 (万円)", value=1820, step=10)
invest_yield = st.sidebar.number_input("投資(NISA等) 年利回り (%)", value=3.0, step=0.1)
invest_surplus = st.sidebar.checkbox("毎年の黒字分を投資に回す", value=True, help="チェックを入れると、生活防衛資金(300万円)を超える黒字を投資残高に追加します。チェックなしだと貯金(金利0%)として積み上がります。")

st.sidebar.markdown("---")
initial_ideco = st.sidebar.number_input("iDeCo残高 (万円)", value=180, step=10)
ideco_monthly = st.sidebar.number_input("iDeCo 毎月掛金 (万円)", value=3.0, step=0.1)
ideco_yield = st.sidebar.number_input("iDeCo 年利回り (%)", value=3.0, step=0.1)

# 3. お子様・教育
st.sidebar.header("👶 お子様・教育")
col1, col2 = st.sidebar.columns(2)
with col1:
    c1_year = st.number_input("第1子 誕生年", value=2025, step=1)
with col2:
    c1_month = st.number_input("第1子 誕生月", value=2, min_value=1, max_value=12)
c1_edu = st.sidebar.selectbox("第1子 教育プラン", list(EDUCATION_COSTS.keys()), index=2)
c1_boarding = st.sidebar.checkbox("第1子 大学は下宿(仕送り)", value=False)

has_child2 = st.sidebar.checkbox("第2子を含める", value=False)
if has_child2:
    col3, col4 = st.sidebar.columns(2)
    with col3:
        c2_year = st.number_input("第2子 誕生年", value=2028, step=1)
    with col4:
        c2_month = st.number_input("第2子 誕生月", value=4, min_value=1, max_value=12)
    c2_edu = st.sidebar.selectbox("第2子 教育プラン", list(EDUCATION_COSTS.keys()), index=0)
    c2_boarding = st.sidebar.checkbox("第2子 大学は下宿(仕送り)", value=False)
else:
    c2_year, c2_month = None, None
    c2_edu = None
    c2_boarding = False

if c1_boarding or c2_boarding:
    boarding_cost_yearly = st.sidebar.number_input("年間仕送り額", value=150, step=10)
else:
    boarding_cost_yearly = 0

# 4. 生活費・ローン
st.sidebar.header("🏠 生活費・住宅")
living_preset_key = st.sidebar.selectbox("生活費プリセット", list(LIVING_PRESETS.keys()), index=1)
living_cost_base = st.sidebar.number_input("年間生活費 (万円)", value=LIVING_PRESETS[living_preset_key], step=10)
fixed_cost_housing = st.sidebar.number_input("固定資産税・維持費 (年額)", value=19.2, step=0.1)
inflation_key = st.sidebar.selectbox("物価上昇率", list(INFLATION_PRESETS.keys()), index=2)
inflation_rate = INFLATION_PRESETS[inflation_key]

st.sidebar.markdown("---")
mortgage_principal = st.sidebar.number_input("借入金額 (万円)", value=6460, step=100)
col_m1, col_m2 = st.sidebar.columns(2)
with col_m1:
    mortgage_start_year = st.number_input("返済開始年", value=2024)
with col_m2:
    mortgage_end_year = st.number_input("完済予定年", value=2059)
mortgage_base_rate = st.sidebar.number_input("基準金利 (%)", value=2.841, step=0.001, format="%.3f")
mortgage_reduction_rate = st.sidebar.number_input("引下幅 (%)", value=2.057, step=0.001, format="%.3f")
mortgage_rate_scenario = MORTGAGE_RATE_SCENARIOS[st.sidebar.selectbox("金利変動シナリオ", list(MORTGAGE_RATE_SCENARIOS.keys()))]

# --- シミュレーション実行 ---
start_year = 2025
last_child_grad_year = c1_year + 23
if has_child2: last_child_grad_year = max(last_child_grad_year, c2_year + 23)
end_year = max(start_year + 35, last_child_grad_year) # 少し長めに
years = list(range(start_year, end_year + 1))

df = pd.DataFrame(index=years)
df['西暦'] = df.index
df['経過年数'] = df['西暦'] - start_year
df['世帯主年齢'] = head_age + df['経過年数']
df['第1子年齢'] = df['西暦'] - c1_year
df['第2子年齢'] = (df['西暦'] - c2_year) if has_child2 else np.nan

# 収入
df['世帯主収入'] = head_income_base * (1 + head_income_growth / 100) ** df['経過年数']
df['世帯収入'] = df['世帯主収入'] + partner_income

# 支出 (Data Editorからの取得は省略し、定数を使用)
df['教育費'] = df['第1子年齢'].apply(lambda x: get_cost(x, EDUCATION_COSTS[c1_edu]))
if has_child2: df['教育費'] += df['第2子年齢'].apply(lambda x: get_cost(x, EDUCATION_COSTS[c2_edu]))

df['養育費'] = df['第1子年齢'].apply(lambda x: get_cost(x, REARING_COSTS['【A】標準プラン']))
if has_child2: df['養育費'] += df['第2子年齢'].apply(lambda x: get_cost(x, REARING_COSTS['【A】標準プラン']))

df['仕送り'] = df['第1子年齢'].apply(lambda x: get_boarding_cost(x, c1_boarding, boarding_cost_yearly))
if has_child2: df['仕送り'] += df['第2子年齢'].apply(lambda x: get_boarding_cost(x, c2_boarding, boarding_cost_yearly))

df['生活費(インフレ込)'] = living_cost_base * (1 + inflation_rate) ** df['経過年数'] + fixed_cost_housing
df['支出計(ローン除)'] = df['教育費'] + df['養育費'] + df['仕送り'] + df['生活費(インフレ込)']

# 資産計算ループ
current_cash = initial_cash * 10000
current_invest = initial_invest * 10000
current_ideco = initial_ideco * 10000
current_loan_balance = mortgage_principal * 10000
current_base_rate = mortgage_base_rate

# ローン初期計算
months_before = max(0, (start_year - mortgage_start_year) * 12 + 3)
monthly_r_init = (mortgage_base_rate - mortgage_reduction_rate) / 100 / 12
if monthly_r_init < 0: monthly_r_init = 0
total_months = (mortgage_end_year - mortgage_start_year) * 12

# 簡易的に開始時残高を計算
for _ in range(months_before):
    if current_loan_balance > 0:
        interest = current_loan_balance * monthly_r_init
        # 元利均等返済の簡易計算
        if total_months > 0:
            if monthly_r_init > 0:
                payment = (current_loan_balance * monthly_r_init * (1+monthly_r_init)**total_months) / ((1+monthly_r_init)**total_months - 1)
            else:
                payment = current_loan_balance / total_months
            current_loan_balance -= (payment - interest)
            total_months -= 1

cash_hist, invest_hist, ideco_hist, loan_hist, payment_hist, balance_hist = [], [], [], [], [], []
bankrupt_year = None

for i, year in enumerate(years):
    # 1. iDeCo (60歳まで積立、その後は運用のみ)
    age = df['世帯主年齢'].iloc[i]
    ideco_add = 0
    if age < 60:
        ideco_add = ideco_monthly * 10000 * 12
    
    # 運用計算: (期首残高 + 積立額/2) * 利回り + 積立額
    # ※積立は毎月行われるため、簡便法として積立額の半分に利回りがつくと仮定
    ideco_gain = (current_ideco + ideco_add / 2) * (ideco_yield / 100)
    current_ideco += ideco_add + ideco_gain
    
    # 2. 住宅ローン
    annual_payment = 0
    if i > 0: current_base_rate = get_rate_fluctuation(mortgage_rate_scenario, current_base_rate)
    applied_rate = max(0, current_base_rate - mortgage_reduction_rate)
    monthly_r = applied_rate / 100 / 12
    
    for _ in range(12):
        if current_loan_balance <= 0: break
        months_left = (mortgage_end_year - year) * 12
        if months_left <= 0: months_left = 1
        
        if monthly_r > 0:
            p = (current_loan_balance * monthly_r * (1+monthly_r)**months_left) / ((1+monthly_r)**months_left - 1)
        else:
            p = current_loan_balance / months_left
        
        interest = current_loan_balance * monthly_r
        current_loan_balance -= (p - interest)
        annual_payment += p
    
    # 3. キャッシュフロー
    income = df['世帯収入'].iloc[i] * 10000
    spending = df['支出計(ローン除)'].iloc[i] * 10000 + annual_payment
    # iDeCo拠出は所得控除等あるが、ここでは単純にキャッシュアウトとして扱う
    cash_flow = income - spending - ideco_add
    
    current_cash += cash_flow
    
    # 4. 資産運用・取り崩し
    # まず投資残高を増やす
    invest_gain = current_invest * (invest_yield / 100)
    current_invest += invest_gain
    
    if current_cash < 0:
        # 赤字なら貯金 -> 投資の順で取り崩し
        shortfall = -current_cash
        current_cash = 0
        if current_invest >= shortfall:
            current_invest -= shortfall
        else:
            # 投資でも足りない -> 破綻
            current_invest = 0 # 全額充当
            # マイナスキャッシュのまま記録（借金状態）
            current_cash = - (shortfall - current_invest) 
            if bankrupt_year is None: bankrupt_year = year
    elif current_cash > 3000000 and invest_surplus:
        # 生活防衛資金(300万)を超える黒字は投資へ
        surplus = current_cash - 3000000
        current_cash = 3000000
        current_invest += surplus

    cash_hist.append(current_cash / 10000)
    invest_hist.append(current_invest / 10000)
    ideco_hist.append(current_ideco / 10000)
    loan_hist.append(current_loan_balance / 10000)
    payment_hist.append(annual_payment / 10000)
    balance_hist.append((income - spending - ideco_add)/10000)

df['貯金'] = cash_hist
df['投資'] = invest_hist
df['iDeCo'] = ideco_hist
df['ローン残高'] = loan_hist
df['ローン返済'] = payment_hist
df['年間収支'] = balance_hist
df['総資産'] = df['貯金'] + df['投資'] + df['iDeCo']
df['純資産'] = df['総資産'] - df['ローン残高']

# --- 表示 ---
st.title("将来家計シミュレーション (修正版)")
st.caption("東京23区外・持家・iDeCo修正・余剰資金投資機能あり")

# サマリー
col1, col2, col3 = st.columns(3)
with col1:
    final_ideco = df['iDeCo'].iloc[-1]
    st.metric("iDeCo最終残高", f"{final_ideco:,.0f} 万円", f"60歳まで月{ideco_monthly}万積立")
with col2:
    final_net = df['純資産'].iloc[-1]
    st.metric("最終純資産", f"{final_net:,.0f} 万円", f"総資産: {df['総資産'].iloc[-1]:,.0f}万")
with col3:
    if bankrupt_year:
        st.error(f"資金ショート: {bankrupt_year}年")
    else:
        st.success("資金ショートなし")

# グラフ
st.subheader("📊 資産推移")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df['西暦'], y=df['総資産'], name='総資産(貯金+投資+iDeCo)', line=dict(color='#4f46e5', width=3)))
fig.add_trace(go.Scatter(x=df['西暦'], y=df['iDeCo'], name='うちiDeCo', line=dict(color='#f59e0b', width=2)))
fig.add_trace(go.Scatter(x=df['西暦'], y=df['投資'], name='うち投資(NISA)', line=dict(color='#10b981', width=2)))
fig.add_trace(go.Scatter(x=df['西暦'], y=df['ローン残高'], name='ローン残高', line=dict(color='#ef4444', dash='dot')))
fig.update_layout(xaxis_title="西暦", yaxis_title="万円", hovermode="x unified")
st.plotly_chart(fig, use_container_width=True)

# データテーブル
st.subheader("📋 詳細データ")
st.dataframe(df[['西暦', '世帯主年齢', '世帯収入', '支出計(ローン除)', 'ローン返済', '年間収支', '貯金', '投資', 'iDeCo', '総資産']].style.format("{:,.0f}"), use_container_width=True)

# AI診断
st.subheader("🤖 AI家計診断")
user_api_key = st.text_input("Gemini APIキー", type="password")
if st.button("診断する") and user_api_key:
    try:
        genai.configure(api_key=user_api_key)
        model = genai.GenerativeModel('gemini-flash-latest')
        
        prompt = f"""
        FPとして家計診断をお願いします。
        
        # 条件
        - 世帯主: {head_age}歳, 年収{head_income_base}万
        - お子様: {c1_year}年生まれ ({c1_edu})
        - 初期資産: 貯金{initial_cash}万, 投資{initial_invest}万, iDeCo{initial_ideco}万
        - iDeCo: 月{ideco_monthly}万 (60歳まで)
        - 投資方針: 余剰資金は投資へ回す
        
        # 結果
        - 最終純資産: {final_net:,.0f}万円
        - iDeCo最終: {final_ideco:,.0f}万円
        - 破綻: {bankrupt_year if bankrupt_year else 'なし'}
        
        辛口で具体的なアドバイスを3点ください。
        """
        with st.spinner("分析中..."):
            st.markdown(model.generate_content(prompt).text)
    except Exception as e:
        st.error(f"エラー: {e}")
