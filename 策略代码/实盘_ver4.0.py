# -*- coding: utf-8 -*-
"""
Created on Thu May 14 14:05:54 2026

@author: Coeur

相较ver3.0加了业绩归因功能
"""
#%% Step 1: 实盘化全局数据准备 —— 本地 Excel 极速直读版
import pandas as pd
import datetime
import warnings
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

warnings.filterwarnings('ignore')

print("【Step 1】开始初始化：正在直接读取本地 Excel 历史数据文件...")

start_fetch_date = "2022-10-01" 
print(f"⚡ 本地直读模式：统一从 {start_fetch_date} 起截取数据...")

# ================= 1.1 读取普林格宏观调仓文件 =================
try:
    pring_df = pd.read_excel(r'C:\Users\Coeur\Desktop\红筹投资\组合构建\菡治\因子合成\更新_王涿\最新普林格调仓明细_至202603(含异象处理_实盘版).xlsx', sheet_name='Sheet1')
    print("✅ 成功读取：普林格宏观调仓明细表")
except Exception as e:
    print(f"❌ 关键宏观文件读取失败，程序强制中断: {e}")
    sys.exit()

# ================= 1.2 读取并清洗本地 Excel 文件 =================
try:
    # 直接使用绝对路径或相对路径读取原始 Excel 文件，并指定 Sheet 名
    # 提示：同花顺导出的数据，Sheet 名默认就是 '收盘价(元)'
    df1 = pd.read_excel(r'C:\Users\Coeur\Desktop\红筹投资\组合构建\实盘\1-5.xlsx', sheet_name='收盘价(元)')
    df2 = pd.read_excel(r'C:\Users\Coeur\Desktop\红筹投资\组合构建\实盘\6-10.xlsx', sheet_name='收盘价(元)')
    
    # 优雅清洗法：强制转换为 datetime。同花顺文件底部的"数据来源:同花顺"等中文文本
    # 在强转时会因为 errors='coerce' 变成 NaT，随后直接 dropna 剔除即可，完美兼容 Excel 格式
    df1['日期'] = pd.to_datetime(df1['日期'], errors='coerce')
    df2['日期'] = pd.to_datetime(df2['日期'], errors='coerce')
    
    df1 = df1.dropna(subset=['日期']).copy()
    df2 = df2.dropna(subset=['日期']).copy()
    
    # 按日期合并这两份表
    df = pd.merge(df1, df2, on='日期', how='outer')
    df = df.set_index('日期').sort_index()
    
    # 强制转为数值 (跳过 ffill，以便下一步准确寻找真实的上市首日)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 清除全空的行
    df = df.dropna(how='all')
    
    # 将长列名映射为标准名称
    rename_map = {
        '沪深300ETF华泰柏瑞': '沪深300ETF',
        '中证1000ETF南方': '中证1000ETF',
        '创业板ETF易方达': '创业板指ETF',
        '恒生科技ETF易方达': '恒生科技ETF',
        '可转债ETF博时': '博时可转债ETF',
        '有色ETF大成': '大成有色ETF',
        '黄金ETF华安': '华安黄金ETF',
        '能源化工ETF建信': '建信能化ETF',
        '豆粕ETF华夏': '华夏豆粕ETF',
        '中欧纯债LOF': '中欧纯债LOF'   
    }
    df = df.rename(columns=rename_map)
    print("✅ 成功加载并合并本地 Excel 历史数据文件！\n")
    
except Exception as e:
    print(f"❌ 读取本地 Excel 文件失败，报错: {e}")
    sys.exit()

# ================= 1.3 木桶效应扫描：提取最短板起始日 =================
print("正在逐一扫描底层资产的有效数据起始日...")
etf_start_dates = {}

for name in df.columns:
    # 自动找到该列第一个非 NaN 值的日期
    first_valid_date = df[name].first_valid_index()
    etf_start_dates[name] = first_valid_date
    if pd.notna(first_valid_date):
        print(f"  - {name:<10} 数据起始: {first_valid_date.strftime('%Y-%m-%d')}")
    else:
        print(f"  - ❌ {name:<10} 未找到有效数据！")

latest_start_date = max(etf_start_dates.values())

print("\n" + "="*60)
print(f"🔍 【木桶短板扫描完成】")
latest_etfs = [name for name, date in etf_start_dates.items() if date == latest_start_date]
print(f"最晚出现数据的底层标的为：{', '.join(latest_etfs)}")
print(f"🎯 统一实盘回测起点将被强制对齐至: 【{latest_start_date.strftime('%Y-%m-%d')}】")
print("="*60 + "\n")

# ================= 1.4 对齐数据与计算收益率 =================
# 对齐前，先执行前向填充 (ffill) 修复中间因停牌等情况产生的缺失值
df = df.ffill()

# 强制截断最晚起始日之前的所有无用数据
prices_all = df[df.index >= latest_start_date]

# 计算日频收益率
ret_all = prices_all.pct_change().fillna(0)

print(f"🎉 Step 1 本地数据准备完毕！共计获取 {len(ret_all)} 个交易日数据。准备进入逻辑运算...\n")
    
#%% Step 2: 实盘化四核引擎构建与宏观权重对齐
print("\n========== 开始执行 Step 2: 构建实盘等权引擎与对齐宏观权重 ==========")

# 1. 定义四大核心引擎的实盘 ETF 成分
eq_etfs = ['沪深300ETF', '中证1000ETF', '创业板指ETF', '恒生科技ETF']
com_etfs = ['大成有色ETF', '华安黄金ETF', '建信能化ETF', '华夏豆粕ETF']
cb_etf = '博时可转债ETF'
cdb_etf = '中欧纯债LOF'  # 更新底仓名称

# 2. 生成引擎级日频收益率 (等权配置)
print("正在合成【股票端】实盘等权宽基引擎 (沪深300/中证1000/创业板/恒生科技)...")
r_eq_daily = ret_all[eq_etfs].mean(axis=1)

print("正在合成【商品端】实盘等权商品引擎 (有色/黄金/能化/豆粕)...")
r_com_daily = ret_all[com_etfs].mean(axis=1)

# 转债与纯债直接取用单只收益率
r_cb_daily = ret_all[cb_etf]
r_cdb_daily = ret_all[cdb_etf]

# 为后续均线计算准备净值序列
nav_eq = (1 + r_eq_daily).cumprod()
nav_com = (1 + r_com_daily).cumprod()

# 3. 处理普林格宏观权重
print("正在抽取并对齐普林格宏观权重...")
pring_df['调仓日期'] = pd.to_datetime(pring_df['调仓日期'])

weights_df = pring_df.set_index('调仓日期')[['沪深300指数', '南华期货:商品指数', '中证基金指数:货币基金', '中证全债指数']]
trading_days = ret_all.index
all_dates = sorted(list(set(trading_days) | set(weights_df.index)))
weights_daily_live = weights_df.reindex(all_dates).ffill().loc[trading_days]

print(f"✅ Step 2 数据合成完毕！实盘引擎底座已就绪，起始日：{trading_days[0].strftime('%Y-%m-%d')}。")

#%% Step 3: 实盘化核心策略大乱斗 —— 纯粹 MA20 基准版与全景可视化
# 设置中文字体，防止图表乱码
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

print("\n========== 开始执行 Step 3: 【实盘四核防御形态】纯粹 MA20 基准版 ==========")

# --- 1. 底层标尺与均线准备 ---
hs300_ret = ret_all['沪深300ETF']
nav_hs300 = (1 + hs300_ret).cumprod()

nav_eq_ma20 = nav_eq.rolling(window=20).mean()
nav_com_ma20 = nav_com.rolling(window=20).mean()

print(f"✅ 避险目标锁定：当触发标准 MA20 跌破时，资金将全额撤离至 [{cdb_etf}]")

# --- 2. 策略回溯运算 ---
dates_all = trading_days
ret_A = []  
ret_C = []  

trades_C_eq, trades_C_com = 0, 0
prev_esc_C_eq, prev_esc_C_com = False, False

daily_active_assets = {}  
is_eq_escape_daily, is_com_escape_daily = {}, {}
hist_w_eq, hist_w_com, hist_w_cb, hist_w_cdb = [], [], [], []

for i, d in enumerate(dates_all):
    w_eq = weights_daily_live['沪深300指数'].loc[d] if pd.notna(weights_daily_live['沪深300指数'].loc[d]) else 0.0
    w_com = weights_daily_live['南华期货:商品指数'].loc[d] if pd.notna(weights_daily_live['南华期货:商品指数'].loc[d]) else 0.0
    w_bond_total = (
        (weights_daily_live['中证基金指数:货币基金'] + weights_daily_live['中证全债指数']).loc[d]
        if pd.notna((weights_daily_live['中证基金指数:货币基金'] + weights_daily_live['中证全债指数']).loc[d])
        else 0.0
    )

    w_cdb_base = min(0.10, w_bond_total)
    w_cb_base = max(0.0, w_bond_total - 0.10)

    is_eq_heavy = w_eq > 0.65
    is_com_heavy = w_com > 0.65

    prev_date = dates_all[i - 1] if i > 0 else dates_all[0]

    e_m_cond = nav_eq.loc[prev_date] >= nav_eq_ma20.loc[prev_date] if pd.notna(nav_eq_ma20.loc[prev_date]) else True
    c_m_cond = nav_com.loc[prev_date] >= nav_com_ma20.loc[prev_date] if pd.notna(nav_com_ma20.loc[prev_date]) else True

    r_e = r_eq_daily.loc[d]
    r_c = r_com_daily.loc[d]
    r_cb = r_cb_daily.loc[d]
    r_cdb = r_cdb_daily.loc[d]

    act_eq = e_m_cond if is_eq_heavy else True
    act_com = c_m_cond if is_com_heavy else True

    if (not act_eq) != prev_esc_C_eq:
        trades_C_eq += 1
        prev_esc_C_eq = (not act_eq)
    if (not act_com) != prev_esc_C_com:
        trades_C_com += 1
        prev_esc_C_com = (not act_com)

    final_w_eq = w_eq if act_eq else 0.0
    final_w_com = w_com if act_com else 0.0
    final_w_cb = w_cb_base
    final_w_cdb = w_cdb_base + (w_eq - final_w_eq) + (w_com - final_w_com)

    ret_C.append(final_w_eq * r_e + final_w_com * r_c + final_w_cb * r_cb + final_w_cdb * r_cdb)
    ret_A.append(w_eq * r_e + w_com * r_c + w_cb_base * r_cb + w_cdb_base * r_cdb)

    active_assets = []
    if final_w_eq > 0: active_assets.append('【股】宽基等权ETF')
    if final_w_com > 0: active_assets.append('【商】商品等权ETF')
    daily_active_assets[d] = active_assets
    is_eq_escape_daily[d] = not act_eq
    is_com_escape_daily[d] = not act_com
    
    hist_w_eq.append(final_w_eq * 100)
    hist_w_com.append(final_w_com * 100)
    hist_w_cb.append(final_w_cb * 100)
    hist_w_cdb.append(final_w_cdb * 100)

# --- 3. 绩效与绘图 ---
nav_A = (1 + pd.Series(ret_A, index=dates_all)).cumprod()
nav_C = (1 + pd.Series(ret_C, index=dates_all)).cumprod()

def get_metrics(nav, name):
    daily = nav.pct_change().fillna(0)
    ann = nav.iloc[-1] ** (252 / len(nav)) - 1
    mdd = (nav / nav.cummax() - 1).min()
    vol = daily.std() * np.sqrt(252)
    sharpe = (ann - 0.02) / vol if vol != 0 else 0.0
    
    # 新增：计算卡玛比率 (年化收益 / 最大回撤的绝对值)
    calmar = ann / abs(mdd) if mdd != 0 else 0.0
    
    # 修改：在返回的字典中加入波动率和卡玛比率
    return {
        '策略': name, 
        '年化': f"{ann*100:.2f}%", 
        '回撤': f"{mdd*100:.2f}%", 
        '夏普': f"{sharpe:.2f}",
        '波动率': f"{vol*100:.2f}%",   # 新增
        '卡玛比率': f"{calmar:.2f}"    # 新增
    }

print("\n========================= 实盘全景回测：(全量逃逸版) 核心绩效 =========================")
print(pd.DataFrame([
    get_metrics(nav_hs300, "沪深300ETF (大盘基准)"),
    get_metrics(nav_A, "理论原版 (无避险满仓)"),
    get_metrics(nav_C, "实盘四核终极版 (全入纯债底仓)")
]).to_string(index=False))

print("\n正在渲染带季度坐标轴的全景甘特图与资金分布...")
all_labels = []
for assets in daily_active_assets.values():
    for a in assets:
        if a not in all_labels:
            all_labels.append(a)
if '【商】商品等权ETF' in all_labels:
    all_labels.remove('【商】商品等权ETF')
    all_labels.insert(0, '【商】商品等权ETF')
label_y = {l: i for i, l in enumerate(all_labels)}
# 把代表净值的 ax3 放第一，甘特图 ax1 放第二，面积图 ax2 放最下面
# 高度比例也对应改成：[净值图1.5, 甘特图1.2, 面积图0.8]
fig, (ax3, ax1, ax2) = plt.subplots(3, 1, figsize=(16, 18), gridspec_kw={'height_ratios': [1.5, 1.2, 0.8]}, sharex=True)
for lbl, y in label_y.items():
    is_in = False
    start = None
    color = 'darkgoldenrod' if '【商】' in lbl else 'limegreen'
    for d in dates_all:
        present = lbl in daily_active_assets[d]
        if present and not is_in:
            is_in = True; start = d
        elif not present and is_in:
            is_in = False
            ax1.broken_barh([(mdates.date2num(start), mdates.date2num(d) - mdates.date2num(start))], (y - 0.3, 0.6), color=color, edgecolor='black', linewidth=0.5)
    if is_in:
        ax1.broken_barh([(mdates.date2num(start), mdates.date2num(dates_all[-1]) - mdates.date2num(start))], (y - 0.3, 0.6), color=color)

for d in dates_all:
    if is_eq_escape_daily[d]: ax1.axvspan(d, d + pd.Timedelta(days=1), color='crimson', alpha=0.15)
    if is_com_escape_daily[d]: ax1.axvspan(d, d + pd.Timedelta(days=1), color='orange', alpha=0.15)

ax1.set_yticks(range(len(all_labels)))
ax1.set_yticklabels(all_labels)
ax1.invert_yaxis()
ax1.set_title('实盘甘特图：主引擎定向避险状态 (红色/橙色背景代表逃逸期)', fontsize=15, fontweight='bold')

y1 = np.array(hist_w_eq)
y2 = y1 + np.array(hist_w_cb)
y3 = y2 + np.array(hist_w_com)
y4 = y3 + np.array(hist_w_cdb)

ax2.fill_between(dates_all, 0,  y1, label='宽基等权ETF(股票)', color='crimson', alpha=0.8, step='post')
ax2.fill_between(dates_all, y1, y2, label='可转债ETF(进攻)', color='darkviolet', alpha=0.8, step='post')
ax2.fill_between(dates_all, y2, y3, label='商品等权ETF', color='darkgoldenrod', alpha=0.8, step='post')
ax2.fill_between(dates_all, y3, y4, label='中欧纯债LOF(蓄水池)', color='steelblue', alpha=0.8, step='post')
ax2.set_ylabel('占比 (%)'); ax2.set_ylim(0, 100); ax2.legend(loc='upper left', ncol=4); ax2.margins(x=0)

ax3.plot(nav_C.index, nav_C, label='实盘四核终极形态 (MA20 避险)', color='crimson', linewidth=3)
ax3.plot(nav_A.index, nav_A, label='理论原版 (无避险)', color='grey', linestyle='--', alpha=0.7)
ax3.plot(nav_hs300.index, nav_hs300, label='沪深300ETF', color='black', linewidth=1, alpha=0.5)
ax3.set_title('实盘对决 (本地源)：不同风控策略下的净值增长曲线', fontsize=15, fontweight='bold')
ax3.legend(loc='upper left'); ax3.grid(True, alpha=0.3)

def quarter_formatter(x, pos):
    try:
        dt = mdates.num2date(x)
        return f"{dt.year}Q{(dt.month - 1) // 3 + 1}"
    except: return ""

ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
ax2.xaxis.set_major_formatter(FuncFormatter(quarter_formatter))
plt.setp(ax2.get_xticklabels(), rotation=45, ha='right', fontsize=11, fontweight='bold')
plt.tight_layout()
plt.show()

# 为后续归因准备 df_daily
r_eq = pd.Series(r_eq_daily, index=dates_all)
r_com = pd.Series(r_com_daily, index=dates_all)
r_cb = pd.Series(r_cb_daily, index=dates_all)
r_cdb = pd.Series(r_cdb_daily, index=dates_all)

s_w_eq = pd.Series(hist_w_eq, index=dates_all) / 100.0
s_w_com = pd.Series(hist_w_com, index=dates_all) / 100.0
s_w_cb = pd.Series(hist_w_cb, index=dates_all) / 100.0
s_w_cdb = pd.Series(hist_w_cdb, index=dates_all) / 100.0

df_daily = pd.DataFrame({'Eq': s_w_eq * r_eq, 'Com': s_w_com * r_com, 'Cb': s_w_cb * r_cb, 'Cdb': s_w_cdb * r_cdb,
    'Strat': pd.Series(ret_C, index=dates_all), 'HS300': hs300_ret.reindex(dates_all).fillna(0)})
df_daily['Prev_NAV'] = nav_C.shift(1).fillna(1.0)
df_daily['Year'] = df_daily.index.year

#%% Step 4: 实盘化四核防御形态 —— 详细调仓合并日志与精准测算记录 (Excel 导出)
print("\n========== 开始执行 Step 4: 生成【实盘详细调仓记录表】 ==========")

merged_records = []
last_state = None

for i, d in enumerate(dates_all):
    w_eq_macro = weights_daily_live['沪深300指数'].loc[d] if pd.notna(weights_daily_live['沪深300指数'].loc[d]) else 0.0
    w_com_macro = weights_daily_live['南华期货:商品指数'].loc[d] if pd.notna(weights_daily_live['南华期货:商品指数'].loc[d]) else 0.0
    w_bond_total = (
        (weights_daily_live['中证基金指数:货币基金'] + weights_daily_live['中证全债指数']).loc[d]
        if pd.notna((weights_daily_live['中证基金指数:货币基金'] + weights_daily_live['中证全债指数']).loc[d]) else 0.0
    )

    w_cdb_base = min(0.10, w_bond_total)
    w_cb_base = max(0.0, w_bond_total - 0.10)

    is_eq_heavy = w_eq_macro > 0.65
    is_com_heavy = w_com_macro > 0.65

    prev_date = dates_all[i - 1] if i > 0 else dates_all[0]
    
    ma20_eq_val = nav_eq_ma20.loc[prev_date]
    ma20_com_val = nav_com_ma20.loc[prev_date]

    e_m_cond = nav_eq.loc[prev_date] >= ma20_eq_val if pd.notna(ma20_eq_val) else True
    c_m_cond = nav_com.loc[prev_date] >= ma20_com_val if pd.notna(ma20_com_val) else True

    act_eq = e_m_cond if is_eq_heavy else True
    act_com = c_m_cond if is_com_heavy else True

    final_w_eq = w_eq_macro if act_eq else 0.0
    final_w_com = w_com_macro if act_com else 0.0
    final_w_cb = w_cb_base
    final_w_cdb = w_cdb_base + (w_eq_macro - final_w_eq) + (w_com_macro - final_w_com)

    current_sig = (w_eq_macro, w_com_macro, act_eq, act_com)
    date_str = d.strftime('%Y-%m-%d')

    if last_state and current_sig == last_state['sig']:
        merged_records[-1]['结束日期'] = date_str
        merged_records[-1]['交易天数'] += 1
    else:
        reason = []
        is_ma20_triggered = False

        if last_state:
            prev_sig = last_state['sig']
            if current_sig[0] != prev_sig[0] or current_sig[1] != prev_sig[1]:
                reason.append("宏观季度调仓")
            if current_sig[2] != prev_sig[2]:
                if not current_sig[2]: reason.append("🔴股端击穿MA20-撤退至纯债")
                else: reason.append("🟢股端收复MA20-买回宽基")
                is_ma20_triggered = True
            if current_sig[3] != prev_sig[3]:
                if not current_sig[3]: reason.append("🟠商端击穿MA20-撤退至纯债")
                else: reason.append("🟡商端收复MA20-买回商品")
                is_ma20_triggered = True
        else:
            reason.append("初始建仓")

        reason_str = " + ".join(reason)

        price_dict = {
            '股端MA20触发价': '-', '商端MA20触发价': '-',
            '【股】合成价格': '-', '【商】合成价格': '-',
            '沪深300(510300.SH)': '-', '中证1000(512100.SH)': '-', 
            '创业板指(159915.SZ)': '-', '恒生科技(513010.SH)': '-',
            '有色ETF(159980.SZ)': '-', '黄金ETF(518880.SH)': '-', 
            '能化ETF(159981.SZ)': '-', '豆粕ETF(159985.SZ)': '-',
            '博时可转债(511380.SH)': '-', '中欧纯债LOF(166016.SZ)': '-'
        }

        if is_ma20_triggered or not last_state or "宏观季度调仓" in reason_str: 
            price_dict['股端MA20触发价'] = f"{ma20_eq_val:.4f}" if is_eq_heavy and pd.notna(ma20_eq_val) else "不适用"
            price_dict['商端MA20触发价'] = f"{ma20_com_val:.4f}" if is_com_heavy and pd.notna(ma20_com_val) else "不适用"
            price_dict['【股】合成价格'] = f"{nav_eq.loc[d]:.4f}"
            price_dict['【商】合成价格'] = f"{nav_com.loc[d]:.4f}"
            price_dict['沪深300(510300.SH)'] = f"{prices_all.loc[d, '沪深300ETF']:.3f}"
            price_dict['中证1000(512100.SH)'] = f"{prices_all.loc[d, '中证1000ETF']:.3f}"
            price_dict['创业板指(159915.SZ)'] = f"{prices_all.loc[d, '创业板指ETF']:.3f}"
            price_dict['恒生科技(513010.SH)'] = f"{prices_all.loc[d, '恒生科技ETF']:.3f}"
            price_dict['有色ETF(159980.SZ)'] = f"{prices_all.loc[d, '大成有色ETF']:.3f}"
            price_dict['黄金ETF(518880.SH)'] = f"{prices_all.loc[d, '华安黄金ETF']:.3f}"
            price_dict['能化ETF(159981.SZ)'] = f"{prices_all.loc[d, '建信能化ETF']:.3f}"
            price_dict['豆粕ETF(159985.SZ)'] = f"{prices_all.loc[d, '华夏豆粕ETF']:.3f}"
            price_dict['博时可转债(511380.SH)'] = f"{prices_all.loc[d, '博时可转债ETF']:.3f}"
            price_dict['中欧纯债LOF(166016.SZ)'] = f"{prices_all.loc[d, '中欧纯债LOF']:.3f}"

        new_record = {
            'sig': current_sig, '开始日期': date_str, '结束日期': date_str, '交易天数': 1, '触发调仓逻辑': reason_str,
            '宽基(股)占比': f"{final_w_eq*100:.1f}%", '商品(商)占比': f"{final_w_com*100:.1f}%",
            '转债(债)占比': f"{final_w_cb*100:.1f}%", '纯债(水库)占比': f"{final_w_cdb*100:.1f}%"
        }
        new_record.update(price_dict)
        merged_records.append(new_record)
        last_state = new_record

final_records = [{k: v for k, v in r.items() if k != 'sig'} for r in merged_records]
df_merged_live = pd.DataFrame(final_records)

try:
    file_path_live = "实盘四核形态_本地版调仓日志.xlsx"
    df_merged_live.to_excel(file_path_live, index=False)
    print(f"\n✅ 成功导出！本地版审计账单已生成至：【{file_path_live}】")
except Exception as e: print(f"\n❌ 导出Excel失败: {e}")

print("\n========== 实盘调仓审计日志 (最近 10 次动作) ==========")
display_cols = ['开始日期', '交易天数', '触发调仓逻辑', '股端MA20触发价', '商端MA20触发价', '【股】合成价格', '【商】合成价格']
print(df_merged_live[display_cols].tail(10).to_string(index=False))

#%% Step 5: 年度收益拆解与最大回撤测算
import matplotlib.ticker as ticker

print("\n========== 开始执行 Step 5: 年度收益拆解与最大回撤全景测算 ==========")

# --- 1. 核心算法：按年严格拆解净值贡献度 ---
annual_stats = []
for year, group in df_daily.groupby('Year'):
    start_nav = group['Prev_NAV'].iloc[0]

    ret_strat = (1 + group['Strat']).prod() - 1
    ret_hs300_year = (1 + group['HS300']).prod() - 1

    cont_eq = (group['Eq'] * group['Prev_NAV']).sum() / start_nav
    cont_com = (group['Com'] * group['Prev_NAV']).sum() / start_nav
    cont_cb = (group['Cb'] * group['Prev_NAV']).sum() / start_nav
    cont_cdb = (group['Cdb'] * group['Prev_NAV']).sum() / start_nav

    annual_stats.append({
        'Year': str(year),
        'Strategy': ret_strat,
        'HS300': ret_hs300_year,
        'Eq': cont_eq,
        'Cb': cont_cb,
        'Com': cont_com,
        'Cdb': cont_cdb
    })

df_annual = pd.DataFrame(annual_stats).set_index('Year')

# --- 2. 绘制图表 1：年度收益大比拼与贡献拆解 ---
print("正在渲染 图表1: 历年收益率对决与四大资产归因分析...")
fig1, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 14))

x = np.arange(len(df_annual))
width = 0.35
ax1.bar(x - width / 2, df_annual['Strategy'], width, label='实盘终极版 (纯债底仓)', color='crimson', edgecolor='black', linewidth=0.5)
ax1.bar(x + width / 2, df_annual['HS300'], width, label='沪深300ETF', color='lightgrey', edgecolor='grey', linewidth=0.5)

ax1.set_xticks(x)
ax1.set_xticklabels(df_annual.index, fontsize=12)
ax1.axhline(0, color='black', linewidth=1)
ax1.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0))
ax1.set_title('实盘检阅：终极防御体系 vs 沪深300 历年自然年度收益率比对', fontsize=16, fontweight='bold', pad=15)
ax1.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=2, fontsize=12)
ax1.grid(True, linestyle=':', alpha=0.6, axis='y')

for i, v in enumerate(df_annual['Strategy']):
    ax1.text(i - width / 2, v + (0.015 if v >= 0 else -0.025), f"{v * 100:.1f}%", ha='center', va='bottom' if v >= 0 else 'top', fontsize=11, fontweight='bold', color='crimson')
for i, v in enumerate(df_annual['HS300']):
    ax1.text(i + width / 2, v + (0.015 if v >= 0 else -0.025), f"{v * 100:.1f}%", ha='center', va='bottom' if v >= 0 else 'top', fontsize=10, color='dimgrey')

assets = ['Eq', 'Cb', 'Com', 'Cdb']
colors = ['crimson', 'darkviolet', 'darkgoldenrod', 'steelblue']
labels = ['【股】贡献度', '【可转债】贡献度', '【商】贡献度', '【纯债】(水库) 贡献度']

pos_bottom = np.zeros(len(df_annual))
neg_bottom = np.zeros(len(df_annual))

for idx, asset in enumerate(assets):
    vals = df_annual[asset].values
    pos_vals = np.maximum(vals, 0)
    neg_vals = np.minimum(vals, 0)
    ax2.bar(x, pos_vals, bottom=pos_bottom, color=colors[idx], label=labels[idx], width=0.5, edgecolor='white', linewidth=0.5)
    ax2.bar(x, neg_vals, bottom=neg_bottom, color=colors[idx], width=0.5, edgecolor='white', linewidth=0.5)
    pos_bottom += pos_vals
    neg_bottom += neg_vals

ax2.plot(x, df_annual['Strategy'], marker='D', markersize=8, color='black', linewidth=1.5, linestyle=':', label='策略该年总净收益')
ax2.set_xticks(x)
ax2.set_xticklabels(df_annual.index, fontsize=12)
ax2.axhline(0, color='black', linewidth=1.5)
ax2.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0))
ax2.set_title('防御内核透视：组合年度总收益的【四大资产驱动力】拆解', fontsize=16, fontweight='bold', pad=15)
ax2.legend(loc='upper center', bbox_to_anchor=(0.5, 1.15), ncol=5, fontsize=11)
ax2.grid(True, linestyle=':', alpha=0.6, axis='y')

plt.tight_layout()
plt.show()

# --- 3. 绘制图表 2：最大回撤全景对比 (水下曲线) ---
print("正在渲染 图表2: 资金曲线的最大回撤 (Underwater Chart) 对决...")
dd_strat = nav_C / nav_C.cummax() - 1
dd_hs300 = nav_hs300 / nav_hs300.cummax() - 1

fig2, ax = plt.subplots(figsize=(16, 7))
ax.fill_between(dd_hs300.index, dd_hs300, 0, color='grey', alpha=0.25, label='沪深300ETF 每日回撤幅度')
ax.plot(dd_hs300.index, dd_hs300, color='grey', linewidth=1, alpha=0.8)
ax.fill_between(dd_strat.index, dd_strat, 0, color='crimson', alpha=0.6, label='终极防御版 (纯债蓄水) 每日回撤幅度')
ax.plot(dd_strat.index, dd_strat, color='darkred', linewidth=1.5)

max_dd_hs300_idx = dd_hs300.idxmin()
max_dd_hs300_val = dd_hs300.min()
ax.scatter(max_dd_hs300_idx, max_dd_hs300_val, color='black', s=80, zorder=5)
ax.annotate(
    f'沪深300 最大回撤\n{max_dd_hs300_val * 100:.2f}%',
    xy=(max_dd_hs300_idx, max_dd_hs300_val),
    xytext=(20, 20),
    textcoords='offset points',
    ha='left',
    va='bottom',
    bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.8),
    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0.2', color='black')
)

max_dd_strat_idx = dd_strat.idxmin()
max_dd_strat_val = dd_strat.min()
ax.scatter(max_dd_strat_idx, max_dd_strat_val, color='darkred', s=80, zorder=5)
ax.annotate(
    f'终极版 最大回撤\n{max_dd_strat_val * 100:.2f}%',
    xy=(max_dd_strat_idx, max_dd_strat_val),
    xytext=(-20, 30),
    textcoords='offset points',
    ha='right',
    va='bottom',
    bbox=dict(boxstyle='round,pad=0.3', fc='white', alpha=0.8),
    arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=-0.2', color='darkred')
)

ax.axhline(0, color='black', linewidth=1.5)
ax.set_title('抗压极限测压：实盘终极版 vs 沪深300 历史回撤水下分布图 (Underwater)', fontsize=17, fontweight='bold', pad=15)
ax.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0))
ax.set_ylabel('距离历史高点的回撤幅度', fontsize=12)
ax.legend(loc='lower left', fontsize=13)
ax.grid(True, linestyle=':', alpha=0.6)
plt.tight_layout()
plt.show()


#%% Step 6: 避险逻辑深度诊断 —— 股、商双引擎 MA20 止损效用透视
print("\n========== 开始执行 Step 6: MA20止损对最大回撤的控制力诊断 (股商双轨版) ==========")

def run_escape_diagnostics(r_asset, escape_flags, asset_name):
    diagnostics = []
    in_escape = False
    escape_start_date = None

    asset_nav_series = (1 + r_asset).cumprod()
    cdb_nav_series = (1 + r_cdb).cumprod()

    for d in dates_all:
        is_escaping = escape_flags[d]

        if is_escaping and not in_escape:
            in_escape = True
            escape_start_date = d

        elif not is_escaping and in_escape:
            in_escape = False
            escape_end_date = d
            
            if escape_start_date in asset_nav_series.index and escape_end_date in asset_nav_series.index:
                mask = (asset_nav_series.index >= escape_start_date) & (asset_nav_series.index <= escape_end_date)
                slice_nav = asset_nav_series[mask]
                
                ret_asset = slice_nav.iloc[-1] / slice_nav.iloc[0] - 1
                mdd_avoided = slice_nav.min() / slice_nav.iloc[0] - 1
                max_runup_missed = slice_nav.max() / slice_nav.iloc[0] - 1
                ret_cdb = cdb_nav_series.loc[escape_end_date] / cdb_nav_series.loc[escape_start_date] - 1

                diagnostics.append({
                    '逃逸开始': escape_start_date.strftime('%Y-%m-%d'),
                    '回归日期': escape_end_date.strftime('%Y-%m-%d'),
                    '避险天数': (escape_end_date - escape_start_date).days,
                    '【成功】躲过的继续暴跌': mdd_avoided,
                    '【代价】错过的深V反弹': max_runup_missed,
                    '底层最终涨跌': ret_asset,
                    '期间纯债收益': ret_cdb
                })

    df_diag = pd.DataFrame(diagnostics)
    
    if not df_diag.empty:
        df_diag_display = df_diag.copy()
        for col in ['【成功】躲过的继续暴跌', '【代价】错过的深V反弹', '底层最终涨跌', '期间纯债收益']:
            df_diag_display[col] = df_diag_display[col].apply(lambda x: f"{x*100:.2f}%")
        
        print(f"\n【{asset_name}端避险回撤控制复盘】共发生 {len(df_diag)} 次完整逃逸：")
        print(df_diag_display.to_string(index=False))

        effective_escape_count = sum(df_diag['【成功】躲过的继续暴跌'] < -0.05)
        
        print(f"\n🛡️ {asset_name}端深度避险有效性统计 (以躲过 >5% 的继续暴跌为有效标准):")
        print(f"在 {len(df_diag)} 次避险中，只有 {effective_escape_count} 次成功帮你躲过了底层超过 5% 的后续暴跌。")
    else:
        print(f"未检测到完整的{asset_name}端避险区间。")

run_escape_diagnostics(r_eq, is_eq_escape_daily, "【股票】")
print("\n" + "="*80)
run_escape_diagnostics(r_com, is_com_escape_daily, "【商品】")


#%% Step 7: 四大底层资产的收益率贡献与全景可视化 (复利精准版)
print("\n========== 开始执行 Step 7: 四大底层资产累计收益贡献度拆解 ==========")

df_daily['Eq_points'] = df_daily['Eq'] * df_daily['Prev_NAV']
df_daily['Com_points'] = df_daily['Com'] * df_daily['Prev_NAV']
df_daily['Cb_points'] = df_daily['Cb'] * df_daily['Prev_NAV']
df_daily['Cdb_points'] = df_daily['Cdb'] * df_daily['Prev_NAV']

cum_Eq = df_daily['Eq_points'].cumsum()
cum_Com = df_daily['Com_points'].cumsum()
cum_Cb = df_daily['Cb_points'].cumsum()
cum_Cdb = df_daily['Cdb_points'].cumsum()

cum_points_df = pd.DataFrame({'股票端': cum_Eq, '商品端': cum_Com, '可转债': cum_Cb, '纯债基': cum_Cdb})

print("正在渲染 图表3: 四大底层资产累计收益贡献度全景面积堆叠图...")
fig3, ax = plt.subplots(figsize=(16, 8))

colors = ['crimson', 'darkgoldenrod', 'darkviolet', 'steelblue']
labels = ['【股】贡献', '【商】贡献', '【可转债】贡献', '【纯债基】(水库) 贡献']

ax.stackplot(
    cum_points_df.index,
    cum_points_df['股票端'], cum_points_df['商品端'], cum_points_df['可转债'], cum_points_df['纯债基'],
    labels=labels, colors=colors, alpha=0.8
)

strat_total_return = nav_C - 1
ax.plot(strat_total_return.index, strat_total_return, label='【实盘终极版】策略总净值走势', color='black', linewidth=2, linestyle='--')

ax.set_title('动力舱透视：四大核心资产对总收益的【绝对拉动点数】堆叠图 (已分配复利)', fontsize=16, fontweight='bold', pad=15)
ax.set_ylabel('累计绝对收益拉动点数', fontsize=12)
ax.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0))
ax.axhline(0, color='black', linewidth=1.5)
ax.legend(loc='upper left', fontsize=12, ncol=5)
ax.grid(True, linestyle=':', alpha=0.6)
ax.set_ylim(bottom=min(0, strat_total_return.min() * 1.1))

try:
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(FuncFormatter(quarter_formatter))
    plt.setp(ax.get_xticklabels(), rotation=45, ha='right', fontsize=11, fontweight='bold')
except: pass 
plt.tight_layout()
plt.show()

# 打印终局核心数据审计表
final_eq = cum_Eq.iloc[-1]
final_com = cum_Com.iloc[-1]
final_cb = cum_Cb.iloc[-1]
final_cdb = cum_Cdb.iloc[-1]

final_total_points = final_eq + final_com + final_cb + final_cdb
pct_eq = final_eq / final_total_points * 100 if final_total_points else 0
pct_com = final_com / final_total_points * 100 if final_total_points else 0
pct_cb = final_cb / final_total_points * 100 if final_total_points else 0
pct_cdb = final_cdb / final_total_points * 100 if final_total_points else 0

print("\n========================= 实盘全景终局归因审计表 (严格复利口径) =========================")
print(f"📈 【股票端】累积绝对拉动: {final_eq*100:>6.2f}%  |  ⭐ 相对总利润贡献占比: {pct_eq:>5.1f}%")
print(f"🛢️ 【商品端】累积绝对拉动: {final_com*100:>6.2f}%  |  ⭐ 相对总利润贡献占比: {pct_com:>5.1f}%")
print(f"🎫 【可转债】累积绝对拉动: {final_cb*100:>6.2f}%  |  ⭐ 相对总利润贡献占比: {pct_cb:>5.1f}%")
print(f"🛡️ 【纯债基】累积绝对拉动: {final_cdb*100:>6.2f}%  |  ⭐ 相对总利润贡献占比: {pct_cdb:>5.1f}%")
print("-" * 75)
print(f"🌟 【策略总净值真收益】: {(nav_C.iloc[-1]-1)*100:>6.2f}%")

# --- 动态分布宏观与利润图 ---
daily_total_points = cum_points_df.sum(axis=1)

# 当总利润极度接近0时，直接置为 NaN，允许零点穿越时自然留白，避免畸形白线
safe_daily_total = daily_total_points.copy()
safe_daily_total[safe_daily_total.abs() < 0.005] = np.nan
df_pct_dynamic = cum_points_df.div(safe_daily_total, axis=0)

fig3_1, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(16, 12), sharex=True, gridspec_kw={'height_ratios': [1, 1.2]})
fig3_1.suptitle('【实盘四核防御形态】宏观底座导航 vs 真实利润贡献穿透', fontsize=18, fontweight='bold', y=0.98)

# ================= 上半部分：宏观底座 (保留方块阶梯优化) =================
w_idx = weights_daily_live.index
w_eq_base = weights_daily_live['沪深300指数'].values
w_com_base = w_eq_base + weights_daily_live['南华期货:商品指数'].values
w_cb_base = w_com_base + weights_daily_live['中证全债指数'].values
w_cdb_base = w_cb_base + weights_daily_live['中证基金指数:货币基金'].values

ax_top.fill_between(w_idx, 0, w_eq_base, label='【股】基准', color='crimson', alpha=0.75, step='post')
ax_top.fill_between(w_idx, w_eq_base, w_com_base, label='【商】基准', color='darkgoldenrod', alpha=0.75, step='post')
ax_top.fill_between(w_idx, w_com_base, w_cb_base, label='【债】基准', color='darkviolet', alpha=0.75, step='post')
ax_top.fill_between(w_idx, w_cb_base, w_cdb_base, label='【现】基准', color='lightslategray', alpha=0.75, step='post')

ax_top.set_title('上篇：原版普林格【理论资金分配】动态演变 (无 MA20 避险干预)', loc='left', fontsize=14, fontweight='bold')
ax_top.set_ylabel('普林格理论占比', fontsize=12)
ax_top.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0))
ax_top.set_ylim(0, 1.0)
ax_top.grid(True, linestyle=':', alpha=0.6)
ax_top.legend(loc='lower center', bbox_to_anchor=(0.5, 1.1), fontsize=11, ncol=4, framealpha=0.9)

# ================= 下半部分：利润贡献 (恢复原版 stackplot) =================
ax_bot.stackplot(
    df_pct_dynamic.index,
    df_pct_dynamic['股票端'], df_pct_dynamic['商品端'], df_pct_dynamic['可转债'], df_pct_dynamic['纯债基'],
    labels=['【股】利润占比', '【商】利润占比', '【可转债】利润占比', '【纯债】利润占比'],
    colors=['crimson', 'darkgoldenrod', 'darkviolet', 'steelblue'], alpha=0.85
)
ax_bot.set_title('下篇：四大引擎【相对总利润贡献占比】的动态演变 (已分配复利)', loc='left', fontsize=14, fontweight='bold')
ax_bot.set_ylabel('利润贡献绝对占比', fontsize=12)
ax_bot.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0))
ax_bot.set_ylim(-0.1, 1.1)
ax_bot.axhline(1.0, color='black', linewidth=1.5, linestyle='--')
ax_bot.axhline(0, color='black', linewidth=1.5)
ax_bot.grid(True, linestyle=':', alpha=0.6)
ax_bot.legend(loc='lower center', bbox_to_anchor=(0.5, 1.1), fontsize=11, ncol=4, framealpha=0.9)

try:
    ax_bot.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax_bot.xaxis.set_major_formatter(FuncFormatter(quarter_formatter))
    plt.setp(ax_bot.get_xticklabels(), rotation=45, ha='right', fontsize=11, fontweight='bold')
except: pass 

plt.subplots_adjust(hspace=0.35)
plt.show()


#%% Step 8: 资金利用率与持仓效率全景诊断 —— 寻找“性价比”之王
print("\n========== 开始执行 Step 8: 资金占用与收益贡献的【非对称性】诊断 ==========")

total_days = len(dates_all)
assets_info = {
    '【股】主引擎': {'w_series': s_w_eq, 'final_pt': final_eq, 'color': 'crimson'},
    '【商】主引擎': {'w_series': s_w_com, 'final_pt': final_com, 'color': 'darkgoldenrod'},
    '【债】进攻转债': {'w_series': s_w_cb, 'final_pt': final_cb, 'color': 'darkviolet'},
    '【水库】纯债基': {'w_series': s_w_cdb, 'final_pt': final_cdb, 'color': 'steelblue'}
}

total_weight_sum = sum([info['w_series'].sum() for info in assets_info.values()])
total_profit_pts = sum([info['final_pt'] for info in assets_info.values()])

stats_list = []
for name, data in assets_info.items():
    w_series = data['w_series']
    f_pt = data['final_pt']
    
    active_days = (w_series > 0).sum()
    time_occupancy = active_days / total_days
    avg_weight = w_series.mean()
    capital_occupancy = w_series.sum() / total_weight_sum 
    profit_contribution = f_pt / total_profit_pts if total_profit_pts != 0 else 0
    efficiency_ratio = profit_contribution / capital_occupancy if capital_occupancy > 0 else 0
    
    stats_list.append({
        '资产区块': name, '活跃天数': active_days, '时间占比': time_occupancy,
        '日均仓位': avg_weight, '资金占用率': capital_occupancy,
        '利润贡献率': profit_contribution, '资金效率倍数': efficiency_ratio, 'color': data['color']
    })

df_eff = pd.DataFrame(stats_list)

print("\n📊 核心资产 [资金时间性价比] 穿透审计报告：")
print("-" * 105)
print(f"{'资产区块':<12} | {'活跃天数':<8} | {'时间占用%':<10} | {'日均平均仓位':<12} | {'资金占用份额':<12} | {'利润贡献份额':<12} | {'⭐ 资金效率倍数':<12}")
print("-" * 105)
for _, row in df_eff.iterrows():
    print(f"{row['资产区块']:<10} | {row['活跃天数']:<8}天 | {row['时间占比']*100:>7.2f}% | "
          f"{row['日均仓位']*100:>10.2f}% | {row['资金占用率']*100:>10.2f}% | "
          f"{row['利润贡献率']*100:>10.2f}% | {row['资金效率倍数']:>8.2f} x")
print("-" * 105)

fig4, ax = plt.subplots(figsize=(14, 7))
x = np.arange(len(df_eff))
width = 0.35

ax.bar(x - width/2, df_eff['资金占用率'], width, label='🧳 资金占用份额 (投入)', color='lightslategrey', edgecolor='black', linewidth=0.5, alpha=0.8)
ax.bar(x + width/2, df_eff['利润贡献率'], width, label='💰 利润贡献份额 (产出)', color=df_eff['color'].tolist(), edgecolor='black', linewidth=1)

ax.set_xticks(x); ax.set_xticklabels(df_eff['资产区块'], fontsize=13, fontweight='bold')
ax.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1.0)); ax.set_ylabel('占比 (%)', fontsize=12)
ax.set_title('核心资产 ROI 诊断：投入 (资金占用) 与 产出 (利润贡献) 的非对称性对比', fontsize=16, fontweight='bold', pad=20)
ax.legend(loc='upper right', fontsize=12); ax.grid(True, linestyle=':', alpha=0.6, axis='y')

for i, (v_cap, v_prof, eff) in enumerate(zip(df_eff['资金占用率'], df_eff['利润贡献率'], df_eff['资金效率倍数'])):
    ax.text(i - width/2, v_cap + 0.01, f"{v_cap*100:.1f}%", ha='center', va='bottom', fontsize=11, color='dimgrey')
    ax.text(i + width/2, v_prof + 0.01, f"{v_prof*100:.1f}%", ha='center', va='bottom', fontsize=11, fontweight='bold', color=df_eff['color'].iloc[i])
    
    bbox_color = 'honeydew' if eff >= 1 else 'mistyrose'
    edge_color = 'green' if eff >= 1 else 'red'
    text_color = 'darkgreen' if eff >= 1 else 'darkred'
    
    ax.annotate(
        f"效率: {eff:.2f}x", xy=(i, max(v_cap, v_prof) + 0.06), ha='center', va='center', fontsize=12, fontweight='bold', color=text_color,
        bbox=dict(boxstyle="round,pad=0.3", fc=bbox_color, ec=edge_color, lw=1.5, alpha=0.9)
    )

ax.set_ylim(0, max(df_eff['资金占用率'].max(), df_eff['利润贡献率'].max()) * 1.35)
plt.tight_layout(); plt.show()
print("\n🎉 实盘性能归因体系完整执行完毕！")
