// ── Chat Rendering / Infinite Scroll / Polling ──
import {
  $, setThreadUnread, refreshAnimaUnread, threadTimeValue,
  mergeThreadsFromSessions, scheduleSaveChatUiState, CONSTANTS,
} from "./ctx.js";

export function createChatRenderer(ctx) {
  const { state, deps } = ctx;
  const { api, t, escapeHtml, renderMarkdown, smartTimestamp, timeStr, renderChatImages } = deps;

  // ── History Message / Tool Call Rendering ──

  function renderHistoryMessage(msg) {
    const ts = msg.ts ? smartTimestamp(msg.ts) : "";
    const tsHtml = ts ? `<span class="chat-ts">${escapeHtml(ts)}</span>` : "";

    if (msg.role === "system") {
      return `<div class="chat-bubble assistant" style="opacity:0.7; font-style:italic;">${escapeHtml(msg.content || "")}${tsHtml}</div>`;
    }
    if (msg.role === "assistant") {
      const content = msg.content ? renderMarkdown(msg.content, state.selectedAnima) : "";
      const toolHtml = renderToolCalls(msg.tool_calls);
      const imagesHtml = renderChatImages(msg.images, { animaName: state.selectedAnima });
      return `<div class="chat-bubble assistant">${content}${imagesHtml}${toolHtml}${tsHtml}</div>`;
    }
    const fromLabel = msg.from_person && msg.from_person !== "human"
      ? `<div style="font-size:0.72rem; opacity:0.7; margin-bottom:2px;">${escapeHtml(msg.from_person)}</div>` : "";
    return `<div class="chat-bubble user">${fromLabel}<div class="chat-text">${escapeHtml(msg.content || "")}</div>${tsHtml}</div>`;
  }

  function renderToolCalls(toolCalls) {
    if (!toolCalls || toolCalls.length === 0) return "";
    return toolCalls.map((tc, idx) => {
      const errorClass = tc.is_error ? " tool-call-error" : "";
      const toolName = escapeHtml(tc.tool_name || "unknown");
      const errorLabel = tc.is_error ? " [ERROR]" : "";
      return `<div class="tool-call-row${errorClass}" data-tool-idx="${idx}"><span class="tool-call-row-icon">\u25B6</span><span class="tool-call-row-name">${toolName}${errorLabel}</span></div>` +
        `<div class="tool-call-detail" data-tool-idx="${idx}" style="display:none;">${renderToolCallDetail(tc)}</div>`;
    }).join("");
  }

  function renderToolCallDetail(tc) {
    let html = "";
    const input = tc.input || "";
    if (input) {
      const inputStr = typeof input === "string" ? input : JSON.stringify(input, null, 2);
      html += `<div class="tool-call-label">\u5165\u529B</div><div class="tool-call-content">${escapeHtml(inputStr)}</div>`;
    }
    const result = tc.result || "";
    if (result) {
      const resultStr = typeof result === "string" ? result : JSON.stringify(result, null, 2);
      html += `<div class="tool-call-label">\u7D50\u679C</div>`;
      if (resultStr.length > CONSTANTS.TOOL_RESULT_TRUNCATE) {
        const truncated = resultStr.slice(0, CONSTANTS.TOOL_RESULT_TRUNCATE);
        html += `<div class="tool-call-content" data-full-result="${escapeHtml(resultStr)}">${escapeHtml(truncated)}...</div>`;
        html += `<button class="tool-call-show-more">\u3082\u3063\u3068\u898B\u308B</button>`;
      } else {
        html += `<div class="tool-call-content">${escapeHtml(resultStr)}</div>`;
      }
    }
    return html;
  }

  function bindToolCallHandlers(container) {
    if (!container) return;
    container.querySelectorAll(".tool-call-row").forEach(row => {
      row.addEventListener("click", () => {
        const idx = row.dataset.toolIdx;
        const detail = row.nextElementSibling;
        if (!detail || detail.dataset.toolIdx !== idx) return;
        const isExpanded = row.classList.contains("expanded");
        row.classList.toggle("expanded", !isExpanded);
        detail.style.display = isExpanded ? "none" : "";
      });
    });
    container.querySelectorAll(".tool-call-show-more").forEach(btn => {
      btn.addEventListener("click", e => {
        e.stopPropagation();
        const contentEl = btn.previousElementSibling;
        if (!contentEl) return;
        const fullResult = contentEl.dataset.fullResult;
        if (fullResult) {
          contentEl.textContent = fullResult;
          delete contentEl.dataset.fullResult;
          btn.remove();
        }
      });
    });
  }

  function renderSessionDivider(session, isFirst) {
    if (isFirst) return "";
    const trigger = session.trigger || "chat";
    let label = "";
    let extraClass = "";
    if (trigger === "heartbeat") {
      label = "\u2764 \u30CF\u30FC\u30C8\u30D3\u30FC\u30C8";
      extraClass = " session-divider-heartbeat";
    } else if (trigger === "cron") {
      label = "\u23F0 Cron\u30BF\u30B9\u30AF";
      extraClass = " session-divider-cron";
    } else {
      label = session.session_start ? smartTimestamp(session.session_start) : "";
    }
    return `<div class="session-divider${extraClass}"><span class="session-divider-label">${escapeHtml(label)}</span></div>`;
  }

  // ── Main Chat Rendering ──

  function renderChat(scrollToBottom = true) {
    const messagesEl = $("chatPageMessages");
    if (!messagesEl) return;

    const name = state.selectedAnima;
    const tid = state.selectedThreadId;
    const history = state.chatHistories[name]?.[tid] || [];
    const hs = state.historyState[name]?.[tid] || { sessions: [], hasMore: false, nextBefore: null, loading: false };

    if (hs.sessions.length === 0 && history.length === 0) {
      messagesEl.innerHTML = hs.loading
        ? `<div class="chat-empty"><span class="tool-spinner"></span> ${t("common.loading")}</div>`
        : `<div class="chat-empty">${t("chat.messages_empty")}</div>`;
      return;
    }

    let topHtml = "";
    if (hs.hasMore) {
      if (hs.loading) topHtml += `<div class="history-loading-more"><span class="tool-spinner"></span> ${t("chat.past_loading")}</div>`;
      topHtml += '<div class="chat-load-sentinel"></div>';
    }

    const prevScrollHeight = messagesEl.scrollHeight;

    let sessionsHtml = "";
    for (let si = 0; si < hs.sessions.length; si++) {
      const session = hs.sessions[si];
      sessionsHtml += renderSessionDivider(session, si === 0);
      if (session.messages) {
        for (const msg of session.messages) sessionsHtml += renderHistoryMessage(msg);
      }
    }

    let liveHtml = "";
    if (history.length > 0) {
      if (hs.sessions.length > 0) {
        liveHtml += `<div class="session-divider"><span class="session-divider-label">${t("chat.current_session")}</span></div>`;
      }
      liveHtml += history.map(m => {
        const ts = m.timestamp ? smartTimestamp(m.timestamp) : "";
        const tsHtml = ts ? `<span class="chat-ts">${escapeHtml(ts)}</span>` : "";

        if (m.role === "thinking") {
          return `<div class="chat-bubble thinking"><span class="thinking-animation">${t("chat.thinking")}</span></div>`;
        }
        if (m.role === "assistant") {
          const streamClass = m.streaming ? " streaming" : "";
          let thinkingHtml = "";
          if (m.thinking && m.thinkingText) {
            thinkingHtml = `<div class="thinking-inline-preview">${escapeHtml(m.thinkingText)}</div>`;
          }
          let content = "";
          if (m.text) {
            content = renderMarkdown(m.text, state.selectedAnima);
          } else if (m.streaming) {
            content = '<span class="cursor-blink"></span>';
          }
          const toolHtml = m.activeTool
            ? `<div class="tool-indicator"><span class="tool-spinner"></span>${t("chat.tool_running", { tool: m.activeTool })}</div>` : "";
          const imagesHtml = renderChatImages(m.images, { animaName: state.selectedAnima });
          return `<div class="chat-bubble assistant${streamClass}">${thinkingHtml}${content}${imagesHtml}${toolHtml}${tsHtml}</div>`;
        }
        const imagesHtml = renderChatImages(m.images);
        const textHtml = m.text ? `<div class="chat-text">${escapeHtml(m.text)}</div>` : "";
        return `<div class="chat-bubble user">${imagesHtml}${textHtml}${tsHtml}</div>`;
      }).join("");
    }

    messagesEl.innerHTML = topHtml + sessionsHtml + liveHtml;
    bindToolCallHandlers(messagesEl);

    if (scrollToBottom) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } else {
      messagesEl.scrollTop += (messagesEl.scrollHeight - prevScrollHeight);
    }
    observeChatSentinel();
  }

  function renderStreamingBubble(msg) {
    const messagesEl = $("chatPageMessages");
    if (!messagesEl) return;
    const bubbles = messagesEl.querySelectorAll(".chat-bubble.assistant.streaming");
    const bubble = bubbles[bubbles.length - 1];
    if (!bubble) return;

    const thinkingHtml = (msg.thinking && msg.thinkingText)
      ? `<div class="thinking-inline-preview">${escapeHtml(msg.thinkingText)}</div>` : "";
    let mainHtml = "";

    if (msg.heartbeatRelay) {
      mainHtml += `<div class="heartbeat-relay-indicator"><span class="tool-spinner"></span>${t("chat.heartbeat_relay")}</div>`;
      if (msg.heartbeatText) mainHtml += `<div class="heartbeat-relay-text">${escapeHtml(msg.heartbeatText)}</div>`;
    } else if (msg.afterHeartbeatRelay && !msg.text) {
      mainHtml = `<div class="heartbeat-relay-indicator"><span class="tool-spinner"></span>${t("chat.heartbeat_relay_done")}</div>`;
    } else if (msg.text) {
      mainHtml = renderMarkdown(msg.text, state.selectedAnima);
    } else {
      mainHtml = '<span class="cursor-blink"></span>';
    }

    let html = `${thinkingHtml}${mainHtml}`;
    if (msg.activeTool) {
      html += `<div class="tool-indicator"><span class="tool-spinner"></span>${t("chat.tool_running", { tool: msg.activeTool })}</div>`;
    }
    bubble.innerHTML = html;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function markResponseComplete(animaName, threadId) {
    if (!animaName || !threadId) return;
    const isActive = state.selectedAnima === animaName && state.selectedThreadId === threadId;
    setThreadUnread(ctx, animaName, threadId, !isActive);
    refreshAnimaUnread(ctx, animaName);
    if (animaName === state.selectedAnima) ctx.controllers.thread.renderThreadTabs();
    ctx.controllers.anima.renderAnimaTabs();
    scheduleSaveChatUiState(ctx);
  }

  // ── Infinite Scroll ──

  function setupChatObserver() {
    if (state.chatObserver) state.chatObserver.disconnect();
    const messagesEl = $("chatPageMessages");
    if (!messagesEl) return;
    state.chatObserver = new IntersectionObserver(
      entries => { for (const entry of entries) if (entry.isIntersecting) loadOlderMessages(); },
      { root: messagesEl, rootMargin: "200px 0px 0px 0px" },
    );
  }

  function observeChatSentinel() {
    if (!state.chatObserver) return;
    const messagesEl = $("chatPageMessages");
    if (!messagesEl) return;
    const sentinel = messagesEl.querySelector(".chat-load-sentinel");
    if (sentinel) state.chatObserver.observe(sentinel);
  }

  async function loadOlderMessages() {
    const name = state.selectedAnima;
    const tid = state.selectedThreadId;
    if (!name) return;
    const hs = state.historyState[name]?.[tid];
    if (!hs || !hs.hasMore || hs.loading) return;
    if (state.streamingContext?.anima === name && state.streamingContext?.thread === tid) return;

    hs.loading = true;
    renderChat(false);

    try {
      const data = await fetchConversationHistory(name, CONSTANTS.HISTORY_PAGE_SIZE, hs.nextBefore, tid);
      if (data && data.sessions && data.sessions.length > 0) {
        hs.sessions = [...data.sessions, ...hs.sessions];
        hs.hasMore = data.has_more || false;
        hs.nextBefore = data.next_before || null;
      } else {
        hs.hasMore = false;
      }
    } catch (err) {
      deps.logger.error("Failed to load older messages", { error: err.message });
    }
    hs.loading = false;
    renderChat(false);
  }

  // ── Conversation History API ──

  async function fetchConversationHistory(animaName, limit = CONSTANTS.HISTORY_PAGE_SIZE, before = null, threadId = "default") {
    let url = `/api/animas/${encodeURIComponent(animaName)}/conversation/history?limit=${limit}`;
    if (before) url += `&before=${encodeURIComponent(before)}`;
    url += `&thread_id=${encodeURIComponent(threadId)}&strict_thread=1`;
    return await api(url);
  }

  // ── Polling ──

  async function pollSelectedChat() {
    const name = state.selectedAnima;
    const tid = state.selectedThreadId || "default";
    if (!name || state.chatPollingInFlight) return;
    if (state.streamingContext?.anima === name && state.streamingContext?.thread === tid) return;
    if (state.chatAbortController) return;

    state.chatPollingInFlight = true;
    try {
      const [conv, sessionsData] = await Promise.all([
        fetchConversationHistory(name, CONSTANTS.HISTORY_PAGE_SIZE, null, tid).catch(() => null),
        api(`/api/animas/${encodeURIComponent(name)}/sessions`).catch(() => null),
      ]);

      if (sessionsData) {
        const prevThreadLastTs = new Map(
          (state.threads[name] || []).map(th => [th.id, threadTimeValue(th.lastTs || "")]),
        );
        mergeThreadsFromSessions(ctx, name, sessionsData);
        for (const th of state.threads[name] || []) {
          if (!th?.id || th.id === tid) continue;
          const prev = prevThreadLastTs.get(th.id) || 0;
          const curr = threadTimeValue(th.lastTs || "");
          if (curr > prev) setThreadUnread(ctx, name, th.id, true);
        }
        refreshAnimaUnread(ctx, name);
        ctx.controllers.anima.renderAnimaTabs();
        ctx.controllers.thread.renderThreadTabs();
      }

      if (!conv || !Array.isArray(conv.sessions)) return;

      if (!state.historyState[name]) state.historyState[name] = {};
      const prev = state.historyState[name][tid] || { sessions: [], hasMore: false, nextBefore: null, loading: false };
      const changed = JSON.stringify(prev.sessions || []) !== JSON.stringify(conv.sessions || []);

      state.historyState[name][tid] = {
        sessions: conv.sessions, hasMore: conv.has_more || false,
        nextBefore: conv.next_before || null, loading: false,
      };

      if (changed) {
        const messagesEl = $("chatPageMessages");
        const shouldStick = messagesEl
          ? (messagesEl.scrollHeight - (messagesEl.scrollTop + messagesEl.clientHeight)) <= 80
          : true;
        renderChat(shouldStick);
      }
    } finally {
      state.chatPollingInFlight = false;
    }
  }

  return {
    renderChat, renderStreamingBubble, markResponseComplete,
    setupChatObserver, observeChatSentinel, fetchConversationHistory,
    pollSelectedChat, renderHistoryMessage, renderSessionDivider,
    bindToolCallHandlers,
  };
}
