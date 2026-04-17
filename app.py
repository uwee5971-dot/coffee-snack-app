import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
from datetime import datetime
import requests
import json

# --- アプリ基本設定 ---
st.set_page_config(page_title="☕️精算ツール🍘", layout="wide")
st.title("☕️精算ツール🍘")

# スプレッドシート接続の確立
conn = st.connection("gsheets", type=GSheetsConnection)

# --- データ操作用関数 ---
def load_data(worksheet_name):
    return conn.read(worksheet=worksheet_name, ttl=0)

def update_data(worksheet_name, df):
    conn.update(worksheet=worksheet_name, data=df)

def get_members():
    df = load_data("members")
    return df["name"].tolist() if not df.empty else []

def send_slack_notification(message):
    """Secretsに登録したURLを使ってSlackに通知を送る"""
    webhook_url = st.secrets["slack_webhook_url"]
    payload = {"text": message}
    try:
        response = requests.post(
            webhook_url, 
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Slack通知に失敗しました: {e}")
        return False

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
                    update_data("expenses", pd.concat([df_exp, new_row], ignore_index=True))
                    st.success("記録完了！")
                else:
                    st.error("入力を確認してください。")
    st.divider()
    st.dataframe(load_data("expenses"), use_container_width=True)

# --- 2. 月末精算 ---
elif menu == "月末精算":
    st.header("📊 月末精算")
    df_exp = load_data("expenses")
    
    if df_exp.empty:
        st.info("データがありません。")
    else:
        coffee_exp = df_exp[df_exp["category"] == "コーヒー関連"].groupby("buyer")["amount"].sum().to_dict()
        snack_exp = df_exp[df_exp["category"] == "お菓子"].groupby("buyer")["amount"].sum().to_dict()
        
        cups, snacks = {}, {}
        for m in members:
            with st.container():
                col_n, col_i, col_c, col_s = st.columns([1.5, 2, 2, 2])
                col_n.markdown(f"👤 **{m}**")
                col_i.caption(f"支出: ☕{int(coffee_exp.get(m, 0))}円 / 🍪{int(snack_exp.get(m, 0))}円")
                cups[m] = col_c.number_input("杯数", min_value=0, key=f"c_{m}")
                snacks[m] = col_s.number_input("個数", min_value=0, key=f"s_{m}")
            st.divider()

        if st.button("🚀 計算を実行する"):
            total_c, total_s = sum(coffee_exp.values()), sum(snack_exp.values())
            sum_c, sum_s = sum(cups.values()), sum(snacks.values())

            if sum_c > 0 or sum_s > 0:
                u_c = total_c / sum_c if sum_c > 0 else 0
                u_s = total_s / sum_s if sum_s > 0 else 0
                st.write(f"単価 ☕: {u_c:.1f}円 / 🍪: {u_s:.1f}円")

                final_list = []
                slack_msg = f"📢 【精算ツール】計算完了！\n☕単価: {u_c:.1f}円 / 🍪単価: {u_s:.1f}円\n\n"
                
                for m in members:
                    paid = coffee_exp.get(m, 0) + snack_exp.get(m, 0)
                    share = (u_c * cups[m]) + (u_s * snacks[m])
                    bal = round(paid - share)
                    final_list.append({"name": m, "total_paid": int(paid), "cups": cups[m], "snacks": snacks[m], "fair_share": round(share), "balance": bal})
                    
                    if bal > 0: status = f"➡️ {abs(bal)}円受取"
                    elif bal < 0: status = f"⬅️ {abs(bal)}円支払"
                    else: status = "✅ 精算不要"
                    slack_msg += f"・{m}: {status}\n"
                
                st.table(pd.DataFrame(final_list))
                st.session_state['last_res'] = pd.DataFrame(final_list)
                st.session_state['slack_text'] = slack_msg
            else:
                st.error("数値を入力してください。")

        if 'slack_text' in st.session_state:
            if st.button("📢 Slackに結果を通知する"):
                if send_slack_notification(st.session_state['slack_text']):
                    st.success("Slackに通知を送信しました！")
                del st.session_state['slack_text']

        if 'last_res' in st.session_state:
            if st.button("今月の清算を確定してリセットする"):
                df_h = load_data("history")
                res = st.session_state['last_res'].copy()
                res["settle_date"] = datetime.now().strftime("%Y-%m-%d")
                update_data("history", pd.concat([df_h, res], ignore_index=True))
                update_data("expenses", pd.DataFrame(columns=["date", "buyer", "category", "item", "amount"]))
                st.success("リセット完了！")
                del st.session_state['last_res']
                st.rerun()

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
                update_data("members", pd.concat([df_m, pd.DataFrame([[new_m]], columns=["name"])], ignore_index=True))
                st.rerun()
    st.divider()
    del_m = st.multiselect("削除", members)
    if st.button("削除実行"):
        df_m = load_data("members")
        update_data("members", df_m[~df_m["name"].isin(del_m)])
        st.rerun()
