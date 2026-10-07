import streamlit as st
import requests
import aiohttp
import asyncio
import json
from dotenv import load_dotenv
import os
load_dotenv()

# Application configuration
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 8000))

API_URL = os.getenv("API_URL", f"http://127.0.0.1:{APP_PORT}")

st.set_page_config(page_title="Agentic RAG", page_icon="🤖", layout="wide")
USER_ID = "user"

# call includes these credentials so retrieval is filtered to this user's real
# Nextcloud groups - same permission model verified against the API directly.
if "nc_username" not in st.session_state:
    st.session_state.nc_username = None
if "nc_password" not in st.session_state:
    st.session_state.nc_password = None
if "nc_groups" not in st.session_state:
    st.session_state.nc_groups = None

# Keep login across page refreshes via URL params (session_state resets on
# refresh). Password re-verified against the API each time -- not just trusted.
if st.session_state.nc_username is None:
    qp_user = st.query_params.get("nc_user")
    qp_pass = st.query_params.get("nc_pass")
    if qp_user and qp_pass:
        try:
            _resp = requests.get(
                f"{API_URL}/documents",
                auth=(qp_user, qp_pass),
                timeout=10,
            )
            if _resp.status_code == 200:
                st.session_state.nc_username = qp_user
                st.session_state.nc_password = qp_pass

                # restore session_id + message history from the URL on refresh. login alone used to persist
                # but the chat itself still reset to empty on every refresh.
                qp_session = st.query_params.get("session_id")
                if qp_session:
                    try:
                        _sess_resp = requests.get(f"{API_URL}/sessions/{qp_session}", timeout=10)
                        if _sess_resp.status_code == 200:
                            st.session_state.session_id = qp_session
                            st.session_state.messages = _sess_resp.json().get("messages", [])
                    except Exception:
                        pass  # session lookup failed - start a fresh chat instead
            else:
                st.query_params.clear()
        except Exception:
            pass  # API unreachable -- fall through to the login form

# Session state init
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# Health check
def check_health(base_url: str):
    try:
        resp = requests.get(f"{base_url}/health", timeout=5)
        if resp.status_code == 200:
            return True
        return False
    except Exception:
        return False


def _normalize_markdown_links(text: str) -> str:
    # The streaming response can sometimes split Markdown links across lines.
    # Normalize only that formatting so Nextcloud links remain clickable.
    return text.replace("]\\r\\n(", "](").replace("]\\n(", "](")

async def stream_chat(message: str, base_url: str):
    request_data = {
        "message": message,
        "session_id": st.session_state.session_id,
        "user_id": USER_ID,
        "search_type": "hybrid",
        "nextcloud_username": st.session_state.nc_username,
        "nextcloud_password": st.session_state.nc_password,
    }

    response_box = st.empty()
    full_response = ""
    retrieved_chunks = []

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{base_url}/chat/stream", json=request_data) as resp:
            if resp.status == 401:
                response_box.error("Nextcloud login failed or expired -- please log in again from the sidebar.")
                st.session_state.nc_username = None
                st.session_state.nc_password = None
                st.session_state.nc_groups = None
                st.query_params.clear()
                return
            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                if data.get("type") == "session":
                    st.session_state.session_id = data.get("session_id")
                    st.query_params["session_id"] = st.session_state.session_id

                elif data.get("type") == "text":
                    content = data.get("content", "")
                    full_response += content
                    response_box.markdown(_normalize_markdown_links(full_response))
                    
                elif data.get("type") == "tools":
                    tools = data.get("tools", [])
                    for tool in tools:
                        tool_name = tool.get("tool_name", "")
                        tool_args = tool.get("args", {})
                        full_response += f"\n [Tool: {tool_name}] \n Args: {tool_args}"
                    response_box.markdown(_normalize_markdown_links(full_response))
                    
                elif data.get("type") == "retrieved_chunks":
                      # Real chunks the AI used to answer — proof it's grounded in a document,
                      # not just the model's own general knowledge.
                    retrieved_chunks = data.get("chunks", [])

                elif data.get("type") == "end":
                    break

    response_box.markdown(_normalize_markdown_links(full_response))
    _render_retrieved_chunks(retrieved_chunks)
    full_response = _normalize_markdown_links(full_response)
    st.session_state.messages.append({
        "role": "assistant",
        "content": full_response,
        "retrieved_chunks": retrieved_chunks,
    })


def _render_retrieved_chunks(chunks: list):
    """Show the real retrieved chunk data under an assistant answer, so a user
    can verify grounding (which document, which chunk, what it actually said,
    how similar it scored) instead of trusting the model's own citation text."""
    if not chunks:
        return
    with st.expander(f"🔍 Retrieved chunks used ({len(chunks)})"):
        for c in chunks:
            st.markdown(f"**{c.get('document_title', 'unknown')}** — score `{c.get('score', 0):.3f}`")
            st.caption(c.get('document_source', ''))
            st.text(c.get('content_preview', ''))
            st.divider()

def run_async(message: str, base_url: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(stream_chat(message, base_url))

# Full page requires Nextcloud login -- no chat/docs visible until logged in.
if not st.session_state.nc_username:
      # Centered login card (side columns are just spacers).
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.title("🤖 Agentic RAG")
        st.subheader("🔐 Log in with your Nextcloud account")

        base_url = st.text_input("API URL", value=API_URL)

        with st.form("nc_login_form"):
            nc_user_input = st.text_input("Nextcloud username")
            nc_pass_input = st.text_input("Nextcloud password", type="password")
            submitted = st.form_submit_button("Log in", use_container_width=True)
            if submitted:
                try:
                    resp = requests.get(
                        f"{base_url}/documents",
                        auth=(nc_user_input, nc_pass_input),
                        timeout=10,
                    )
                    if resp.status_code == 401:
                        st.error("Invalid Nextcloud username or password.")
                    elif resp.status_code != 200:
                        st.error(f"Login check failed (HTTP {resp.status_code}).")
                    else:
                        st.session_state.nc_username = nc_user_input
                        st.session_state.nc_password = nc_pass_input
                        st.session_state.messages = []
                        st.session_state.session_id = None
                        st.session_state.base_url = base_url
                        st.query_params["nc_user"] = nc_user_input
                        st.query_params["nc_pass"] = nc_pass_input
                        st.rerun()
                except Exception as e:
                    st.error(f"Could not reach API: {e}")

    st.stop()

# Everything below only renders after a successful login
base_url = st.session_state.get("base_url", API_URL)

# Sidebar
with st.sidebar:
    st.success(f"Logged in as **{st.session_state.nc_username}**")
    if st.button("Log out"):
        st.session_state.nc_username = None
        st.session_state.nc_password = None
        st.session_state.nc_groups = None
        st.session_state.messages = []
        st.session_state.session_id = None
        st.session_state.pop("doc_list", None)
        st.query_params.clear()
        st.rerun()

    st.divider()

    st.header("Settings")
    base_url = st.text_input("API URL", value=base_url)

    if st.button("Check Health"):
        if check_health(base_url):
            st.success("API is healthy")
        else:
            st.error("API not reachable")

    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.session_state.session_id = None
        st.query_params.pop("session_id", None)
        st.rerun()

    st.divider()

    # "My Documents" -- what this logged-in user's chat is actually allowed to
    # search, using the same /documents + allowed_groups filter as /chat.
    st.header("📄 My Documents")
    if st.button("Refresh document list"):
        try:
            auth = (st.session_state.nc_username, st.session_state.nc_password)
            resp = requests.get(f"{base_url}/documents", auth=auth, timeout=10)
            if resp.status_code == 401:
                st.error("Nextcloud login expired -- please log in again.")
                st.session_state.nc_username = None
                st.session_state.nc_password = None
                st.query_params.clear()
                st.rerun()
            elif resp.status_code == 200:
                docs = resp.json().get("documents", [])
                st.session_state["doc_list"] = docs
            else:
                st.error(f"Failed to load documents (HTTP {resp.status_code}).")
        except Exception as e:
            st.error(f"Could not reach API: {e}")

    for doc in st.session_state.get("doc_list", []):
        title = doc.get("title", "Untitled")
        source = doc.get("source", "")
        chunks = doc.get("chunk_count", "?")
        st.caption(f"📄 **{title}** — {source} ({chunks} chunks)")

    st.divider()

   # Manual sync button — forces an immediate re-scan instead of waiting for the
   # background poller. Only 'admin' group can trigger it (enforced in api.py).
    st.header("🔄 Nextcloud Sync")
    st.caption("New/changed files in Nextcloud are picked up automatically in the background. Use this to force an immediate sync instead of waiting.")
    if st.button("Sync Nextcloud now", use_container_width=True):
        try:
            auth = (st.session_state.nc_username, st.session_state.nc_password)
            resp = requests.post(f"{base_url}/admin/sync-nextcloud", auth=auth, timeout=120)
            if resp.status_code == 403:
                st.error("Only Nextcloud 'admin' group members can trigger a sync.")
            elif resp.status_code == 401:
                st.error("Nextcloud login expired -- please log in again.")
                st.session_state.nc_username = None
                st.session_state.nc_password = None
                st.query_params.clear()
                st.rerun()
            elif resp.status_code == 200:
                stats = resp.json()
                st.success(
                    f"Sync complete — {stats['new']} new, {stats['updated']} updated, "
                    f"{stats['unchanged']} unchanged, {stats['failed']} failed."
                )
            else:
                st.error(f"Sync failed (HTTP {resp.status_code}).")
        except Exception as e:
            st.error(f"Could not reach API: {e}")

# Main chat
st.title("Agentic RAG")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(_normalize_markdown_links(msg["content"]))
        _render_retrieved_chunks(msg.get("retrieved_chunks", []))

if prompt := st.chat_input("Ask something..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            run_async(prompt, base_url)