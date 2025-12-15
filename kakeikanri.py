import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import google.generativeai as genai
import datetime

# --- ページ設定 ---
st.set_page_config(
    page_title="将来家計シミュレーション (決定版)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- パスワード認証機能 ---
def check_password():
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

# --- 定数データ (東京都市部・2025年版) ---
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

# --- サイドバー設定 (操作順序を最適化) ---
st.sidebar.title("🛠️ 条件設定")

# 1. お子様・教育 (最優先)
st.sidebar.header("👶 1. お子様・教育プラン")
col1, col2 = st.sidebar.columns(2)
with col1:
    c1_year = st.number_input("第1子 誕生年", value=2025, step=1)
with col2:
    c1_month = st.number_input("第1子 誕生月", value=2, min_value=1, max_value=12)
c1_edu = st.sidebar.selectbox("第1子 教育コース", list(EDUCATION_COSTS.keys()), index=2)
c1_boarding = st.sidebar.checkbox("第1子 大学は下宿(仕送り)", value=False)

has_child2 = st.sidebar.checkbox("第2子を含める", value=False)
if has_child2:
    col3, col4 = st.sidebar.columns(2)
    with col3:
        c2_year = st.number_input("第2子 誕生年", value=2028, step=1)
    with col4:
        c2_month = st.number_input("第2子 誕生月", value=4, min_value=1, max_value=12)
    c2_edu = st.sidebar.selectbox("第2子 教育コース", list(EDUCATION_COSTS.keys()), index=0)
    c2_boarding = st.sidebar.checkbox("第2子 大学は下宿(仕送り)", value=False)
else:
    c2_year, c2_month = None, None
    c2_edu = None
    c2_boarding = False

if c1_boarding or c2_boarding:
    boarding_cost_yearly = st.sidebar.number_input("年間仕送り額 (家賃+生活費)", value=150, step=10)
else:
    boarding_cost_yearly = 0

# 2. 収入・生活費
st.sidebar.header("👛 2. 収入・生活費")
head_age = st.sidebar.number_input("世帯主 現在年齢", value=35, step=1)
income_preset_key = st.sidebar.selectbox("世帯主収入シナリオ", list(INCOME_PRESETS.keys()), index=1)
income_preset = INCOME_PRESETS[income_preset_key]
head_income_base = st.sidebar.number_input("世帯主 現在年収 (万円)", value=income_preset['base'], step=10)
head_income_growth = st.sidebar.number_input("世帯主 昇給率 (%/年)", value=income_preset['growth'], step=0.1)
partner_income = st.sidebar.number_input("パートナー年収 (万円)", value=0, step=10)

st.sidebar.markdown("---")
living_preset_key = st.sidebar.selectbox("生活費 (住居費別)", list(LIVING_PRESETS.keys()), index=1)
living_cost_base = st.sidebar.number_input("年間生活費 (万円)", value=LIVING_PRESETS[living_preset_key], step=10)
fixed_cost_housing = st.sidebar.number_input("固定資産税・維持費 (年額)", value=19.2, step=0.1)
inflation_key = st.sidebar.selectbox("物価上昇率", list(INFLATION_PRESETS.keys()), index=2)
inflation_rate = INFLATION_PRESETS[inflation_key]

# 3. 住宅ローン
st.sidebar.header("🏠 3. 住宅ローン")
mortgage_principal = st.sidebar.number_input("借入金額 (万円)", value=6460, step=100)
col_m1, col_m2 = st.sidebar.columns(2)
with col_m1:
    mortgage_start_year = st.number_input("返済開始年", value=2024)
with col_m2:
    mortgage_end_year = st.number_input("完済予定年", value=2059)
mortgage_base_rate = st.sidebar.number_input("基準金利 (%)", value=2.841, step=0.001, format="%.3f")
mortgage_reduction_rate = st.sidebar.number_input("引下幅 (%)", value=2.057, step=0.001, format="%.3f")
mortgage_rate_scenario = MORTGAGE_RATE_SCENARIOS[st.sidebar.selectbox("金利変動シナリオ", list(MORTGAGE_RATE_SCENARIOS.keys()))]

# 4. 資産・運用 (詳細は下部に)
st.sidebar.header("💰 4. 現在資産・iDeCo")
initial_cash = st.sidebar.number_input("現在の貯金 (万円)", value=380, step=10)
initial_invest = st.sidebar.number_input("現在の投資 (万円)", value=1820, step=10)
invest_yield = st.sidebar.number_input("投資(NISA) 年利回り (%)", value=3.0, step=0.1)
invest_surplus = st.sidebar.checkbox("毎年の黒字分を投資に回す", value=True)

st.sidebar.markdown("---")
initial_ideco = st.sidebar.number_input("iDeCo残高 (万円)", value=180, step=10)
ideco_monthly = st.sidebar.number_input("iDeCo 毎月掛金 (万円)", value=3.0, step=0.1)
ideco_yield = st.sidebar.number_input("iDeCo 年利回り (%)", value=3.0, step=0.1)

# --- シミュレーション実行 ---
start_year = 2025
last_child_grad_year = c1_year + 23
if has_child2: last_child_grad_year = max(last_child_grad_year, c2_year + 23)
end_year = max(start_year + 35, last_child_grad_year) 
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

# 支出
df['教育費'] = df['第1子年齢'].apply(lambda x: get_cost(x, EDUCATION_COSTS[c1_edu]))
if has_child2: df['教育費'] += df['第2子年齢'].apply(lambda x: get_cost(x, EDUCATION_COSTS[c2_edu]))

df['養育費'] = df['第1子年齢'].apply(lambda x: get_cost(x, REARING_COSTS['【A】標準プラン']))
if has_child2: df['養育費'] += df['第2子年齢'].apply(lambda x: get_cost(x, REARING_COSTS['【A】標準プラン']))

df['仕送り'] = df['第1子年齢'].apply(lambda x: get_boarding_cost(x, c1_boarding, boarding_cost_yearly))
if has_child2: df['仕送り'] += df['第2子年齢'].apply(lambda x: get_boarding_cost(x, c2_boarding, boarding_cost_yearly))

df['生活費(インフレ込)'] = living_cost_base * (1 + inflation_rate) ** df['経過年数'] + fixed_cost_housing
df['支出計(ローン除)'] = df['教育費'] + df['養育費'] + df['仕送り'] + df['生活費(インフレ込)']

# 資産計算
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

for _ in range(months_before):
    if current_loan_balance > 0:
        interest = current_loan_balance * monthly_r_init
        if total_months > 0:
            if monthly_r_init > 0:
                payment = (current_loan_balance * monthly_r_init * (1+monthly_r_init)**total_months) / ((1+monthly_r_init)**total_months - 1)
            else:
                payment = current_loan_balance / total_months
            current_loan_balance -= (payment - interest)
            total_months -= 1

cash_hist, invest_hist, ideco_hist, loan_hist, payment_hist, balance_hist = [], [], [], [], [], []
bankrupt_year = None
min_assets_val = float('inf')
min_assets_year = start_year

for i, year in enumerate(years):
    # iDeCo (60歳まで)
    age = df['世帯主年齢'].iloc[i]
    ideco_add = 0
    if age < 60:
        ideco_add = ideco_monthly * 10000 * 12
    ideco_gain = (current_ideco + ideco_add / 2) * (ideco_yield / 100)
    current_ideco += ideco_add + ideco_gain
    
    # 住宅ローン
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
    
    # キャッシュフロー
    income = df['世帯収入'].iloc[i] * 10000
    spending = df['支出計(ローン除)'].iloc[i] * 10000 + annual_payment
    cash_flow = income - spending - ideco_add
    current_cash += cash_flow
    
    # 投資計算
    invest_gain = current_invest * (invest_yield / 100)
    current_invest += invest_gain
    
    if current_cash < 0:
        shortfall = -current_cash
        current_cash = 0
        if current_invest >= shortfall:
            current_invest -= shortfall
        else:
            current_invest = 0
            current_cash = - (shortfall - current_invest) 
            if bankrupt_year is None: bankrupt_year = year
    elif current_cash > 3000000 and invest_surplus:
        surplus = current_cash - 3000000
        current_cash = 3000000
        current_invest += surplus

    total_assets = current_cash + current_invest + current_ideco
    
    # 資産最小値の更新 (破綻していない場合のみ、あるいは借金も含めて)
    if total_assets < min_assets_val:
        min_assets_val = total_assets
        min_assets_year = year

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
df['教育・養育・仕送り'] = df['教育費'] + df['養育費'] + df['仕送り']

# --- メインコンテンツ ---
st.title("将来家計シミュレーション 📊")
st.markdown("お子様の教育費と、将来の老後資金の安全性を確認します。")

# 重要指標 (KPI)
total_child_cost = df['教育・養育・仕送り'].sum()
final_net_assets = df['純資産'].iloc[-1]
min_assets_disp = df.loc[df['西暦'] == min_assets_year, '総資産'].values[0]

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="👶 教育・養育費の総額",
        value=f"{total_child_cost:,.0f} 万円",
        delta="仕送り含む" if (c1_boarding or c2_boarding) else "自宅通学"
    )

with col2:
    if bankrupt_year:
        st.error(f"⚠️ {bankrupt_year}年に資金ショート")
    else:
        # 安全性の判定
        is_safe = min_assets_disp > 300 # 300万以上あれば安全圏と仮定
        color = "normal" if is_safe else "off"
        st.metric(
            label="📉 最も家計が苦しくなる時期",
            value=f"{min_assets_year}年",
            delta=f"残高 {min_assets_disp:,.0f} 万円",
            delta_color=color
        )

with col3:
    st.metric(
        label="👴 老後時点の純資産 (ローン完済後)",
        value=f"{final_net_assets:,.0f} 万円",
        help="iDeCo、NISA、貯金の合計からローン残高を引いた額"
    )

# グラフ
st.subheader("📈 資産推移シミュレーション")
st.caption("太い青線（総資産）が赤点線（ローン残高）を上回っている状態を維持することが目標です。")

fig = go.Figure()

# 構成要素を積み上げ面グラフ風に見せるか、単に線を引くか。ここでは見やすさ重視でライン。
fig.add_trace(go.Scatter(
    x=df['西暦'], y=df['総資産'], 
    name='<b>総資産 (貯金+投資+iDeCo)</b>', 
    line=dict(color='#2563eb', width=4), # 強調
    hovertemplate='%{y:,.0f}万円'
))

fig.add_trace(go.Scatter(
    x=df['西暦'], y=df['投資'], 
    name='うち投資(NISA)', 
    line=dict(color='#10b981', width=1),
    stackgroup='one' # 積み上げ表示
))
fig.add_trace(go.Scatter(
    x=df['西暦'], y=df['iDeCo'], 
    name='うちiDeCo', 
    line=dict(color='#f59e0b', width=1),
    stackgroup='one'
))
fig.add_trace(go.Scatter(
    x=df['西暦'], y=df['貯金'], 
    name='うち貯金', 
    line=dict(color='#93c5fd', width=1),
    stackgroup='one'
))

# ローンは別軸的に表示
fig.add_trace(go.Scatter(
    x=df['西暦'], y=df['ローン残高'], 
    name='ローン残高', 
    line=dict(color='#ef4444', dash='dot', width=2)
))

fig.update_layout(
    xaxis_title="西暦", 
    yaxis_title="金額 (万円)", 
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)
st.plotly_chart(fig, use_container_width=True)

# データテーブル
with st.expander("詳細データを見る"):
    display_cols = ['西暦', '世帯主年齢', '第1子年齢', '世帯収入', '教育・養育・仕送り', '生活費(インフレ込)', 'ローン返済', '年間収支', '総資産']
    st.dataframe(df[display_cols].style.format("{:,.0f}"), use_container_width=True)

# AI診断
st.markdown("---")
st.subheader("🤖 AIファイナンシャル・プランナー")
user_api_key = st.text_input("Gemini APIキー (入力すると診断開始)", type="password")

if st.button("家計診断を実行する") and user_api_key:
    try:
        genai.configure(api_key=user_api_key)
        model = genai.GenerativeModel('gemini-flash-latest')
        
        boarding_status = "なし"
        if c1_boarding or c2_boarding: boarding_status = f"あり(年{boarding_cost_yearly}万)"
        
        prompt = f"""
        あなたは優秀なFPです。以下のシミュレーション結果に基づき、ユーザーの「教育費」と「老後資金」のバランスについてアドバイスしてください。

        # ユーザー属性
        - 世帯主: {head_age}歳, 現在年収{head_income_base}万
        - 子供: 第1子{c1_year}年生まれ({c1_edu}) / 仕送り{boarding_status}
        - 現在資産: 貯金{initial_cash}万, 投資{initial_invest}万, iDeCo{initial_ideco}万

        # シミュレーション結果
        - 教育・養育費総額: {total_child_cost:,.0f}万円
        - 最も苦しい時期: {min_assets_year}年 (資産残高 {min_assets_disp:,.0f}万円)
        - 老後純資産(最終): {final_net_assets:,.0f}万円
        - 破綻: {'あり' if bankrupt_year else 'なし'}

        # アドバイスのポイント
        1. 教育費のピーク時に家計が持ちこたえられるか？
        2. 教育費をかけすぎた結果、老後資金が不足していないか？
        3. iDeCoやNISAの活用バランスは適切か？
        
        簡潔に3点にまとめてください。
        """
        with st.spinner("AIが家計状況を分析中..."):
            st.markdown(model.generate_content(prompt).text)
    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
