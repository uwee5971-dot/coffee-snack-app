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

def get_member_map():
    """名前とSlack IDの対応表を作成する"""
    df = load_data("members")
    if df.empty:
        return {}
    # slack_id列がない、または空の場合の処理
    if "slack_id" not in df.columns:
        df["slack_id"] = ""
    return pd.Series(df.slack_id.values, index=df.name).to_dict()

def send_slack_notification(message):
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
member_map = get_member_map()
members = list(member_map.keys())

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
        # スプレッドシートのカラム名に合わせて修正が必要な場合があります（例：buyer, amount）
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
                slack_msg = f"📢 【精算ツール】計算完了！各自精算をお願いします。\n☕単価: {u_c:.1f}円 / 🍪単価: {u_s:.1f}円\n\n"
                
                for m in members:
                    paid = coffee_exp.get(m, 0) + snack_exp.get(m, 0)
                    share = (u_c * cups[m]) + (u_s * snacks[m])
                    bal = round(paid - share)
                    final_list.append({"name": m, "total_paid": int(paid), "cups": cups[m], "snacks": snacks[m], "fair_share": round(share), "balance": bal})
                    
                    # メンションの作成
                    sid = member_map.get(m)
                    # IDがあればメンション形式に、なければ名前にする
                    mention = f"<@{sid}>" if pd.notna(sid) and sid != "" else m
                    
                    if bal > 0: status = f"➡️ **{abs(bal)}円 受取**"
                    elif bal < 0: status = f"⬅️ **{abs(bal)}円 支払**"
                    else: status = "✅ 精算不要"
                    slack_msg += f"・{mention}: {status}\n"
                
                st.table(pd.DataFrame(final_list))
                st.session_state['last_res'] = pd.DataFrame(final_list)
                st.session_state['slack_text'] = slack_msg
            else:
                st.error("数値を入力してください。")

        if 'slack_text' in st.session_state:
            if st.button("📢 Slackにメンション付き通知を飛ばす"):
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

# --- 3. 過去の履歴 ---
elif menu == "過去の履歴":
    st.header("📜 過去の清算記録")
    st.dataframe(load_data("history"), use_container_width=True)

# --- 4. メンバー管理 ---
else:
    st.header("⚙️ メンバー管理")
    with st.form("add_member"):
        new_m = st.text_input("追加する名前")
        new_sid = st.text_input("SlackメンバーID (例: U012345678)")
        if st.form_submit_button("追加"):
            if new_m:
                df_m = load_data("members")
                if "slack_id" not in df_m.columns:
                    df_m["slack_id"] = ""
                
                if new_m not in df_m["name"].tolist():
                    new_row = pd.DataFrame([[new_m, new_sid]], columns=["name", "slack_id"])
                    update_data("members", pd.concat([df_m, new_row], ignore_index=True))
                    st.rerun()
                else:
                    st.error("その名前は既に登録されています。")
    st.divider()
    del_m = st.multiselect("削除", members)
    if st.button("削除実行"):
        df_m = load_data("members")
        update_data("members", df_m[~df_m["name"].isin(del_m)])
        st.rerun()
