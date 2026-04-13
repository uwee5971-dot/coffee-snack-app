import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# --- アプリ基本設定 ---
st.set_page_config(page_title="☕精算ツール🍘", layout="wide")
st.title("☕精算ツール🍘")

# スプレッドシート接続の確立
conn = st.connection("gsheets", type=GSheetsConnection)

# --- データ操作用関数（スプレッドシート版） ---
def load_data(worksheet_name):
    """指定したワークシートのデータを読み込む"""
    return conn.read(worksheet=worksheet_name, ttl=0) # ttl=0で常に最新を取得

def update_data(worksheet_name, df):
    """指定したワークシートにデータを上書き保存する"""
    conn.update(worksheet=worksheet_name, data=df)

# メンバーリストの取得
def get_members():
    df = load_data("members")
    return df["name"].tolist() if not df.empty else []

# --- メニュー構成 ---
menu = st.sidebar.selectbox("メニューを選択", ["支出記録 / 出納表", "月末精算", "過去の履歴", "メンバー管理"])
members = get_members()

# --- 1. 支出記録 / 出納表 ---
if menu == "支出記録 / 出納表":
    st.header("📝 支出記録")
    if not members:
        st.warning("先に「メンバー管理」からメンバーを登録してください。")
    else:
        with st.form("expense_form", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            with col1: date = st.date_input("日付", datetime.now())
            with col2: buyer = st.selectbox("購入者", members)
            with col3: category = st.radio("カテゴリー", ["コーヒー関連", "お菓子"])
            
            col4, col5 = st.columns(2)
            with col4: item = st.text_input("項目", placeholder="豆、牛乳、チョコなど")
            with col5: amount = st.number_input("金額 (円)", min_value=0, step=10)
            
            if st.form_submit_button("記録する"):
                if item and amount > 0:
                    df_exp = load_data("expenses")
                    new_row = pd.DataFrame([[date.strftime('%Y-%m-%d'), buyer, category, item, amount]], columns=df_exp.columns)
                    df_updated = pd.concat([df_exp, new_row], ignore_index=True)
                    update_data("expenses", df_updated)
                    st.success("スプレッドシートに記録しました！")
                else:
                    st.error("入力を確認してください。")

    st.divider()
    st.subheader("📊 今月の購入履歴")
    st.dataframe(load_data("expenses"), use_container_width=True)

# --- 2. 月末精算 ---
elif menu == "月末精算":
    st.header("📊 月末精算")
    df_exp = load_data("expenses")
    
    if df_exp.empty:
        st.info("今月の支出データがありません。")
    else:
        coffee_exp_map = df_exp[df_exp["カテゴリー"] == "コーヒー関連"].groupby("buyer")["amount"].sum().to_dict()
        snack_exp_map = df_exp[df_exp["カテゴリー"] == "お菓子"].groupby("buyer")["amount"].sum().to_dict()
        
        cups = {}
        snacks = {}
        for m in members:
            c_p = int(coffee_exp_map.get(m, 0))
            s_p = int(snack_exp_map.get(m, 0))
            with st.container():
                col_n, col_i, col_c, col_s = st.columns([1.5, 2, 2, 2])
                with col_n: st.markdown(f"👤 **{m}**")
                with col_i: st.caption(f"支出済: ☕{c_p}円 / 🍪{s_p}円")
                with col_c: cups[m] = st.number_input(f"杯数", min_value=0, key=f"cup_{m}")
                with col_s: snacks[m] = st.number_input(f"個数", min_value=0, key=f"snk_{m}")
            st.divider()

        if st.button("🚀 計算を実行する"):
            total_c = sum(coffee_exp_map.values())
            total_s = sum(snack_exp_map.values())
            sum_cups = sum(cups.values())
            sum_snks = sum(snacks.values())

            if sum_cups > 0 or sum_snks > 0:
                u_p_c = total_c / sum_cups if sum_cups > 0 else 0
                u_p_s = total_s / sum_snks if sum_snks > 0 else 0
                st.write(f"☕単価: {u_p_c:.1f}円 ｜ 🍪単価: {u_p_s:.1f}円")

                final_list = []
                for m in members:
                    paid = coffee_exp_map.get(m, 0) + snack_exp_map.get(m, 0)
                    share = (u_p_c * cups[m]) + (u_p_s * snacks[m])
                    bal = paid - share
                    final_list.append({"name": m, "total_paid": int(paid), "cups": cups[m], "snacks": snacks[m], "fair_share": round(share), "balance": round(bal)})

                res_df = pd.DataFrame(final_list)
                st.table(res_df)
                st.session_state['last_res'] = res_df
                
                for res in final_list:
                    if res["balance"] > 0: st.success(f"✅ {res['name']}：{res['balance']}円 受取")
                    elif res["balance"] < 0: st.error(f"💸 {res['name']}：{abs(res['balance'])}円 支払")
            else:
                st.error("杯数または個数を入力してください。")

        if 'last_res' in st.session_state:
            if st.button("今月の清算を確定してリセットする"):
                # 履歴の保存
                df_hist = load_data("history")
                new_res = st.session_state['last_res'].copy()
                new_res["settle_date"] = datetime.now().strftime("%Y-%m-%d")
                df_hist_updated = pd.concat([df_hist, new_res], ignore_index=True)
                update_data("history", df_hist_updated)
                # 出納表のリセット（ヘッダーのみ残す）
                empty_exp = pd.DataFrame(columns=["date", "buyer", "category", "item", "amount"])
                update_data("expenses", empty_exp)
                st.success("履歴を保存し、出納表をリセットしました！")
                del st.session_state['last_res']
                st.rerun()

# --- 3. 過去の履歴 / 4. メンバー管理 ---
elif menu == "過去の履歴":
    st.header("📜 過去の清算記録")
    st.dataframe(load_data("history"), use_container_width=True)

else:
    st.header("⚙️ メンバー管理")
    new_m = st.text_input("追加する名前")
    if st.button("追加"):
        if new_m:
            df_m = load_data("members")
            if new_m not in df_m["name"].tolist():
                new_row = pd.DataFrame([[new_m]], columns=["name"])
                update_data("members", pd.concat([df_m, new_row], ignore_index=True))
                st.success(f"{new_m}さんを登録しました。")
                st.rerun()
    st.divider()
    del_m = st.multiselect("削除する名前", members)
    if st.button("削除"):
        df_m = load_data("members")
        df_m = df_m[~df_m["name"].isin(del_m)]
        update_data("members", df_m)
        st.rerun()
