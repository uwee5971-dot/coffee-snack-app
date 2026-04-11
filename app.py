import streamlit as st
import pandas as pd
import os
from datetime import datetime

# --- 設定：データ保存用ファイル ---
MEMBER_FILE = "members_list.txt"
EXPENSE_FILE = "expenses_log.csv"
HISTORY_FILE = "settlement_history.csv"

# --- データ操作用関数 ---
def load_members():
    """メンバーリストの読み込み [cite: 5, 10, 24]"""
    if os.path.exists(MEMBER_FILE):
        with open(MEMBER_FILE, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return ["Aさん", "Bさん"]

def save_members(member_list):
    """メンバーリストの保存 [cite: 5, 10, 24]"""
    with open(MEMBER_FILE, "w", encoding="utf-8") as f:
        for m in member_list:
            f.write(f"{m}\n")

def load_expenses():
    """支出履歴の読み込み [cite: 8, 18, 19, 22]"""
    if os.path.exists(EXPENSE_FILE):
        return pd.read_csv(EXPENSE_FILE)
    return pd.DataFrame(columns=["日付", "購入者", "カテゴリー", "項目", "金額"])

def save_expense(date, name, category, item, amount):
    """支出履歴の保存 [cite: 8, 18, 19, 22]"""
    df = load_expenses()
    new_data = pd.DataFrame([[date, name, category, item, amount]], 
                            columns=["日付", "購入者", "カテゴリー", "項目", "金額"])
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(EXPENSE_FILE, index=False)

def finalize_and_reset(results_df):
    """履歴保存とリセット [cite: 9, 15, 24]"""
    results_df["清算日"] = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(HISTORY_FILE):
        history_df = pd.read_csv(HISTORY_FILE)
        history_df = pd.concat([history_df, results_df], ignore_index=True)
    else:
        history_df = results_df
    history_df.to_csv(HISTORY_FILE, index=False)
    if os.path.exists(EXPENSE_FILE):
        os.remove(EXPENSE_FILE)

# --- アプリ構成 ---
st.set_page_config(page_title="☕精算ツール🍘", layout="wide") # アプリ名の更新
st.title("☕精算ツール🍘") # メインタイトルの更新

# サイドバーメニュー [cite: 5, 21, 24]
menu = st.sidebar.selectbox("メニューを選択", ["出納表（都度入力）", "計算（月末）", "過去の履歴", "メンバー管理"])
members = load_members()

# --- 1. 出納表（都度入力）画面 ---
if menu == "出納表（都度入力）":
    st.header("📝 支出の記録")
    with st.form("expense_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1: date = st.date_input("日付", datetime.now())
        with col2: buyer = st.selectbox("購入者", members)
        with col3: category = st.radio("カテゴリー", ["コーヒー関連", "お菓子"]) # カテゴリー分け [cite: 37, 38]
        
        col4, col5 = st.columns(2)
        with col4: item = st.text_input("項目", placeholder="豆、牛乳、チョコなど")
        with col5: amount = st.number_input("金額 (円)", min_value=0, step=10)
        
        if st.form_submit_button("記録する"):
            if item and amount > 0:
                save_expense(date, buyer, category, item, amount)
                st.success(f"{category}の「{item}」を記録しました！")
            else:
                st.error("入力を確認してください。")

    st.divider()
    st.subheader("📊 今月の購入履歴")
    df_exp = load_expenses()
    st.dataframe(df_exp, use_container_width=True)

# --- 2. 割り勘計算（月末）画面 ---
elif menu == "計算（月末）":
    st.header("📊 月次計算")
    df_exp = load_expenses()
    
    # カテゴリー別に自動集計 [cite: 22, 37, 38]
    coffee_exp_map = df_exp[df_exp["カテゴリー"] == "コーヒー関連"].groupby("購入者")["金額"].sum().to_dict()
    snack_exp_map = df_exp[df_exp["カテゴリー"] == "お菓子"].groupby("購入者")["金額"].sum().to_dict()
    
    st.info("各自が「飲んだ杯数」と「食べたお菓子の数」を入力してください。")
    
    cups = {}
    snacks = {}
    
    for m in members:
        c_exp = coffee_exp_map.get(m, 0)
        s_exp = snack_exp_map.get(m, 0)
        
        with st.container():
            col_name, col_info, col_cup, col_snack = st.columns([1.5, 2, 2, 2])
            with col_name:
                st.markdown(f"👤 **{m}**")
            with col_info:
                st.caption(f"支出済: コーヒー{int(c_exp)}円 / 菓子{int(s_exp)}円")
            with col_cup:
                cups[m] = st.number_input(f"飲んだ杯数", min_value=0, key=f"cup_{m}")
            with col_snack:
                snacks[m] = st.number_input(f"食べたお菓子", min_value=0, key=f"snack_{m}")
        st.divider()

    if st.button("🚀 計算を実行する"):
        total_c_exp = sum(coffee_exp_map.values())
        total_s_exp = sum(snack_exp_map.values())
        total_cups = sum(cups.values())
        total_snacks = sum(snacks.values())

        if total_cups > 0 or total_snacks > 0:
            # コーヒーとお菓子それぞれの単価計算 [cite: 1, 12, 37, 38]
            unit_price_c = total_c_exp / total_cups if total_cups > 0 else 0
            unit_price_s = total_s_exp / total_snacks if total_snacks > 0 else 0
            
            st.write(f"☕ コーヒー単価: **{unit_price_c:.1f}円/杯** ｜ 🍪 お菓子単価: **{unit_price_s:.1f}円/個**")

            final_data = []
            for m in members:
                paid = coffee_exp_map.get(m, 0) + snack_exp_map.get(m, 0)
                # 本来の負担額を合算して計算 [cite: 12, 38]
                fair_share = (unit_price_c * cups[m]) + (unit_price_s * snacks[m])
                balance = paid - fair_share
                
                final_data.append({
                    "名前": m,
                    "合計支出額": int(paid),
                    "コーヒー杯数": cups[m],
                    "お菓子個数": snacks[m],
                    "本来の負担額": round(fair_share),
                    "清算額": round(balance)
                })

            res_df = pd.DataFrame(final_data)
            st.table(res_df)
            st.session_state['last_result'] = res_df
            
            # 清算アクションの判定 [cite: 1, 12, 28]
            for res in final_data:
                val = res["清算額"]
                if val > 0: st.success(f"✅ **{res['名前']}**：{val}円 受け取ってください。")
                elif val < 0: st.error(f"💸 **{res['名前']}**：{abs(val)}円 支払ってください。")
        else:
            st.error("杯数または個数を入力してください。")

    # 確定・リセットボタン [cite: 22, 24, 28, 29]
    if 'last_result' in st.session_state:
        if st.button("今月の清算を確定してリセットする"):
            finalize_and_reset(st.session_state['last_result'])
            del st.session_state['last_result']
            st.success("データをリセットしました！")
            st.rerun()

# --- 3. 過去の履歴画面 ---
elif menu == "過去の履歴":
    st.header("📜 過去の清算記録")
    if os.path.exists(HISTORY_FILE):
        st.dataframe(pd.read_csv(HISTORY_FILE), use_container_width=True)
    else: st.write("履歴はありません。")

# --- 4. メンバー管理画面 ---
else:
    st.header("⚙️ メンバー管理")
    new_member = st.text_input("追加する名前")
    if st.button("追加"):
        if new_member and new_member not in members:
            members.append(new_member)
            save_members(members)
            st.rerun()
    st.divider()
    to_delete = st.multiselect("削除するメンバー", members)
    if st.button("削除"):
        save_members([m for m in members if m not in to_delete])
        st.rerun()