// ── Thread CRUD / Tab Controller ──────────────
import {
  $, isTabOpen, refreshAnimaUnread, clearUnreadForActiveThread,
  setThreadUnread, threadTimeValue, scheduleSaveChatUiState,
  CONSTANTS,
} from "./ctx.js";

export function createThreadController(ctx) {
  const { state, deps } = ctx;
  const { escapeHtml } = deps;

  function renderThreadTabs() {
    const container = $("chatThreadTabs");
    if (!container || !state.selectedAnima) return;

    const list = state.threads[state.selectedAnima] || [{ id: "default", label: "メイン", unread: false }];
    const defaultThread = list.find(th => th.id === "default") || { id: "default", label: "メイン", unread: false };
    const nonDefault = list.filter(th => th.id !== "default").sort((a, b) => {
      const diff = threadTimeValue(b.lastTs || "") - threadTimeValue(a.lastTs || "");
      if (diff !== 0) return diff;
      return String(a.label || "").localeCompare(String(b.label || ""), "ja");
    });

    let visibleNonDefault = nonDefault.slice(0, CONSTANTS.THREAD_VISIBLE_NON_DEFAULT);
    const activeHidden = state.selectedThreadId !== "default" && !visibleNonDefault.some(th => th.id === state.selectedThreadId);
    if (activeHidden) {
      const activeThread = nonDefault.find(th => th.id === state.selectedThreadId);
      if (activeThread) {
        visibleNonDefault = [activeThread, ...visibleNonDefault.slice(0, Math.max(0, CONSTANTS.THREAD_VISIBLE_NON_DEFAULT - 1))];
        const unique = new Map();
        for (const th of visibleNonDefault) unique.set(th.id, th);
        visibleNonDefault = Array.from(unique.values());
      }
    }
    const visibleIds = new Set(visibleNonDefault.map(th => th.id));
    const hiddenThreads = nonDefault.filter(th => !visibleIds.has(th.id));

    let html = "";
    const visible = [defaultThread, ...visibleNonDefault];
    for (const th of visible) {
      const activeClass = th.id === state.selectedThreadId ? " active" : "";
      const star = th.unread ? ' <span class="tab-star" aria-label="unread">★</span>' : "";
      const closeBtn = th.id !== "default"
        ? ` <button type="button" class="thread-tab-close" data-thread="${escapeHtml(th.id)}" title="スレッドを閉じる" aria-label="閉じる">&times;</button>`
        : "";
      html += `<span class="thread-tab-wrap"><button type="button" class="thread-tab${activeClass}" data-thread="${escapeHtml(th.id)}">${escapeHtml(th.label)}${star}</button>${closeBtn}</span>`;
    }

    if (hiddenThreads.length > 0) {
      html += `<span class="thread-more-wrap">
        <label class="thread-more-label" for="chatThreadMoreSelect">他 ${hiddenThreads.length} 件</label>
        <select id="chatThreadMoreSelect" class="thread-more-select">
          <option value="">スレッドを選択...</option>
          ${hiddenThreads.map(th => `<option value="${escapeHtml(th.id)}">${escapeHtml(th.label)}${th.unread ? " ★" : ""}</option>`).join("")}
        </select>
      </span>`;
    }
    html += `<button type="button" class="thread-tab-new" id="chatNewThreadBtn" title="新しいスレッド">＋</button>`;

    container.innerHTML = html;

    container.querySelectorAll(".thread-tab").forEach(btn => {
      btn.addEventListener("click", e => {
        const tid = e.target.dataset.thread;
        if (tid) selectThread(tid);
      });
    });
    container.querySelectorAll(".thread-tab-close").forEach(btn => {
      btn.addEventListener("click", e => {
        e.stopPropagation();
        const tid = e.target.dataset.thread;
        if (tid) closeThread(tid);
      });
    });
    const newBtn = $("chatNewThreadBtn");
    if (newBtn) newBtn.addEventListener("click", () => createNewThread());

    const moreSelect = $("chatThreadMoreSelect");
    if (moreSelect) {
      moreSelect.addEventListener("change", e => {
        const tid = e.target.value;
        if (tid) selectThread(tid);
        e.target.value = "";
      });
    }
  }

  async function selectThread(threadId) {
    if (threadId === state.selectedThreadId) return;
    state.selectedThreadId = threadId;
    state.activeThreadByAnima[state.selectedAnima] = threadId;
    clearUnreadForActiveThread(ctx, state.selectedAnima, threadId);
    refreshAnimaUnread(ctx, state.selectedAnima);
    ctx.controllers.anima.renderAnimaTabs();
    renderThreadTabs();

    const name = state.selectedAnima;
    if (!name) return;

    const hs = state.historyState[name]?.[threadId];
    const needLoad = !hs || hs.sessions.length === 0;
    ctx.controllers.renderer.renderChat();

    if (needLoad) {
      try {
        const conv = await ctx.controllers.renderer.fetchConversationHistory(name, CONSTANTS.HISTORY_PAGE_SIZE, null, threadId);
        if (!state.historyState[name]) state.historyState[name] = {};
        if (conv && conv.sessions && conv.sessions.length > 0) {
          state.historyState[name][threadId] = {
            sessions: conv.sessions, hasMore: conv.has_more || false,
            nextBefore: conv.next_before || null, loading: false,
          };
        } else {
          state.historyState[name][threadId] = { sessions: [], hasMore: false, nextBefore: null, loading: false };
        }
      } catch {
        if (!state.historyState[name]) state.historyState[name] = {};
        state.historyState[name][threadId] = { sessions: [], hasMore: false, nextBefore: null, loading: false };
      }
    }
    ctx.controllers.renderer.renderChat();
    scheduleSaveChatUiState(ctx);
  }

  function createNewThread() {
    if (!state.selectedAnima) return;
    const threadId = crypto.randomUUID().slice(0, 8);
    const list = state.threads[state.selectedAnima] || [{ id: "default", label: "メイン", unread: false }];
    list.push({ id: threadId, label: "新しいスレッド", unread: false });
    state.threads[state.selectedAnima] = list;

    if (!state.chatHistories[state.selectedAnima]) state.chatHistories[state.selectedAnima] = {};
    state.chatHistories[state.selectedAnima][threadId] = [];

    if (!state.historyState[state.selectedAnima]) state.historyState[state.selectedAnima] = {};
    state.historyState[state.selectedAnima][threadId] = { sessions: [], hasMore: false, nextBefore: null, loading: false };

    renderThreadTabs();
    selectThread(threadId);
    scheduleSaveChatUiState(ctx);
  }

  function closeThread(threadId) {
    if (threadId === "default" || !state.selectedAnima) return;
    const list = state.threads[state.selectedAnima];
    if (!list) return;
    const idx = list.findIndex(th => th.id === threadId);
    if (idx < 0) return;

    list.splice(idx, 1);
    delete state.chatHistories[state.selectedAnima]?.[threadId];
    delete state.historyState[state.selectedAnima]?.[threadId];

    if (state.selectedThreadId === threadId) {
      state.selectedThreadId = "default";
      state.activeThreadByAnima[state.selectedAnima] = "default";
    }
    refreshAnimaUnread(ctx, state.selectedAnima);
    ctx.controllers.anima.renderAnimaTabs();
    renderThreadTabs();
    ctx.controllers.renderer.renderChat();
    scheduleSaveChatUiState(ctx);
  }

  return { renderThreadTabs, selectThread, createNewThread, closeThread };
}
