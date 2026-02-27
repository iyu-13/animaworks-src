// ── Streaming / Send / Queue Controller ────────
import {
  $, saveDraft, clearDraft, chatInputMaxHeight,
  scheduleSaveChatUiState, CONSTANTS,
} from "./ctx.js";

const SEND_BTN_ICONS = {
  send: `<svg class="chat-send-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 19V5M5 12l7-7 7 7" /></svg>`,
  stop: `<svg class="chat-send-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="5" y="5" width="14" height="14" rx="2.5" /></svg>`,
  interrupt: `<span class="chat-send-icon-group" aria-hidden="true"><svg class="chat-send-icon chat-send-icon-square" viewBox="0 0 24 24" focusable="false"><rect x="5" y="5" width="14" height="14" rx="2.5" /></svg><svg class="chat-send-icon" viewBox="0 0 24 24" focusable="false"><path d="M12 19V5M5 12l7-7 7 7" /></svg></span>`,
};

export function createStreamingController(ctx) {
  const { state, deps } = ctx;
  const { t, escapeHtml, logger, streamChat, fetchActiveStream, fetchStreamProgress } = deps;

  function setSendButtonIcon(sendBtn, mode) {
    sendBtn.innerHTML = SEND_BTN_ICONS[mode] || SEND_BTN_ICONS.send;
  }

  function updateSendButton() {
    const sendBtn = $("chatPageSendBtn");
    const queueBtn = $("chatPageQueueBtn");
    const inputVal = $("chatPageInput")?.value?.trim() || "";
    const hasInput = inputVal.length > 0;
    const isChatStreaming = state.streamingContext?.anima === state.selectedAnima &&
      state.streamingContext?.thread === state.selectedThreadId;

    if (queueBtn) queueBtn.disabled = !hasInput || !state.selectedAnima;
    if (!sendBtn) return;

    sendBtn.classList.remove("stop", "interrupt");
    if (!isChatStreaming) {
      setSendButtonIcon(sendBtn, "send");
      sendBtn.disabled = !state.selectedAnima || (!hasInput && state.pendingQueue.length === 0);
    } else if (hasInput) {
      setSendButtonIcon(sendBtn, "send");
      sendBtn.disabled = false;
    } else if (state.pendingQueue.length > 0) {
      setSendButtonIcon(sendBtn, "interrupt");
      sendBtn.classList.add("interrupt");
      sendBtn.disabled = false;
    } else {
      setSendButtonIcon(sendBtn, "stop");
      sendBtn.classList.add("stop");
      sendBtn.disabled = false;
    }
  }

  function showPendingIndicator() {
    const bar = $("chatPagePending");
    const list = $("chatPagePendingList");
    const label = $("chatPagePendingLabel");
    if (!bar || !list) return;
    if (state.pendingQueue.length === 0) { bar.style.display = "none"; return; }
    if (label) label.textContent = `${t("chat.queue_label")} (${state.pendingQueue.length})`;
    list.innerHTML = state.pendingQueue.map((p, i) => {
      const txt = escapeHtml(p.text.length > 60 ? p.text.slice(0, 60) + "\u2026" : p.text);
      const img = p.images?.length ? ` <span style="opacity:0.6">(+${p.images.length} images)</span>` : "";
      return `<div class="pending-queue-item" data-idx="${i}"><span class="pending-queue-item-num">${i + 1}.</span><span class="pending-queue-item-text">${txt || "(images only)"}${img}</span><button class="pending-queue-item-del" data-idx="${i}" type="button">\u2715</button></div>`;
    }).join("");
    bar.style.display = "";

    list.onclick = e => {
      const delBtn = e.target.closest(".pending-queue-item-del");
      if (delBtn) {
        e.stopPropagation();
        state.pendingQueue.splice(parseInt(delBtn.dataset.idx, 10), 1);
        showPendingIndicator();
        updateSendButton();
        return;
      }
      const item = e.target.closest(".pending-queue-item");
      if (item) {
        const removed = state.pendingQueue.splice(parseInt(item.dataset.idx, 10), 1)[0];
        if (removed) {
          const input = $("chatPageInput");
          if (input) {
            input.value = removed.text;
            input.style.height = "auto";
            input.style.height = Math.min(input.scrollHeight, chatInputMaxHeight()) + "px";
            input.focus();
          }
        }
        showPendingIndicator();
        updateSendButton();
      }
    };
  }

  function hidePendingIndicator() {
    const bar = $("chatPagePending");
    if (bar) bar.style.display = "none";
  }

  function addToQueue() {
    const input = $("chatPageInput");
    if (!input) return;
    const msg = input.value.trim();
    const hasImages = state.imageInputManager && state.imageInputManager.getImageCount() > 0;
    if (!msg && !hasImages) return;
    state.pendingQueue.push({
      text: msg,
      images: state.imageInputManager?.getPendingImages() || [],
      displayImages: state.imageInputManager?.getDisplayImages() || [],
    });
    input.value = "";
    input.style.height = "auto";
    saveDraft(state.selectedAnima, "");
    state.imageInputManager?.clearImages();
    showPendingIndicator();
    updateSendButton();
  }

  function stopStreaming() {
    if (!state.selectedAnima) return;
    if (state.chatAbortController) state.chatAbortController.abort();
    fetch(`/api/animas/${encodeURIComponent(state.selectedAnima)}/interrupt`, { method: "POST" }).catch(() => {});
  }

  function interruptAndSendPending() {
    stopStreaming();
  }

  function submitChat() {
    const input = $("chatPageInput");
    if (!input) return;
    const msg = input.value.trim();
    const hasImages = state.imageInputManager && state.imageInputManager.getImageCount() > 0;
    const isChatStreaming = state.streamingContext?.anima === state.selectedAnima &&
      state.streamingContext?.thread === state.selectedThreadId;

    if (!isChatStreaming) {
      if (msg || hasImages) {
        state.pendingQueue.push({
          text: msg,
          images: state.imageInputManager?.getPendingImages() || [],
          displayImages: state.imageInputManager?.getDisplayImages() || [],
        });
        input.value = "";
        input.style.height = "auto";
        saveDraft(state.selectedAnima, "");
        state.imageInputManager?.clearImages();
      }
      if (state.pendingQueue.length === 0) return;
      const next = state.pendingQueue.shift();
      showPendingIndicator();
      if (state.pendingQueue.length === 0) hidePendingIndicator();
      sendChat(next.text, { images: next.images, displayImages: next.displayImages });
      return;
    }

    if (msg || hasImages) {
      state.pendingQueue.push({
        text: msg,
        images: state.imageInputManager?.getPendingImages() || [],
        displayImages: state.imageInputManager?.getDisplayImages() || [],
      });
      input.value = "";
      input.style.height = "auto";
      saveDraft(state.selectedAnima, "");
      state.imageInputManager?.clearImages();
      showPendingIndicator();
      updateSendButton();
      return;
    }

    if (state.pendingQueue.length > 0) { interruptAndSendPending(); return; }
    stopStreaming();
  }

  async function sendChat(message, overrideImages = null) {
    const name = state.selectedAnima;
    const images = overrideImages?.images || state.imageInputManager?.getPendingImages() || [];
    const displayImages = overrideImages?.displayImages || state.imageInputManager?.getDisplayImages() || [];
    if (!name || (!message.trim() && images.length === 0)) return;

    const currentAnima = state.animas.find(p => p.name === name);
    if (currentAnima?.status === "bootstrapping" || currentAnima?.bootstrapping) {
      const msgs = $("chatPageMessages");
      if (msgs) {
        const el = document.createElement("div");
        el.className = "chat-bubble assistant";
        el.textContent = t("chat.bootstrapping");
        msgs.appendChild(el);
        msgs.scrollTop = msgs.scrollHeight;
      }
      return;
    }

    const tid = state.selectedThreadId;
    if (!state.chatHistories[name]) state.chatHistories[name] = {};
    if (!state.chatHistories[name][tid]) state.chatHistories[name][tid] = [];
    const history = state.chatHistories[name][tid];

    const threadList = state.threads[name] || [];
    const threadEntry = threadList.find(th => th.id === tid);
    if (threadEntry && threadEntry.label === "新しいスレッド" && message.trim()) {
      threadEntry.label = message.trim().slice(0, 20) + (message.trim().length > 20 ? "..." : "");
      ctx.controllers.thread.renderThreadTabs();
      scheduleSaveChatUiState(ctx);
    }

    const sendTs = new Date().toISOString();
    history.push({ role: "user", text: message, images: displayImages, timestamp: sendTs });
    if (threadEntry) threadEntry.lastTs = sendTs;
    const streamingMsg = { role: "assistant", text: "", streaming: true, activeTool: null, timestamp: sendTs, thinkingText: "", thinking: false };
    history.push(streamingMsg);
    ctx.controllers.renderer.renderChat();

    const input = $("chatPageInput");
    state.streamingContext = { anima: name, thread: tid };
    state.chatAbortController = new AbortController();
    updateSendButton();
    ctx.controllers.anima.renderAnimaTabs();
    if (input) input.placeholder = t("chat.message_to", { name });
    if (!overrideImages) state.imageInputManager?.clearImages();

    ctx.controllers.activity.addLocalActivity("chat", name, `${t("chat.user_prefix")} ${message}`);

    try {
      let sendSucceeded = false;
      const currentUser = localStorage.getItem("animaworks_user") || "human";
      const bodyObj = { message, from_person: currentUser, thread_id: tid };
      if (images.length > 0) bodyObj.images = images;
      const body = JSON.stringify(bodyObj);

      logger.debug(`_sendChat: starting stream for ${name} msg_len=${message.length}`);
      await streamChat(name, body, state.chatAbortController.signal, {
        onTextDelta: text => {
          streamingMsg.afterHeartbeatRelay = false;
          streamingMsg.text += text;
          logger.debug(`onTextDelta: delta_len=${text.length} total_len=${streamingMsg.text.length}`);
          ctx.controllers.renderer.renderStreamingBubble(streamingMsg);
        },
        onToolStart: toolName => { logger.debug(`onToolStart: ${toolName}`); streamingMsg.activeTool = toolName; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onToolEnd: () => { logger.debug("onToolEnd"); streamingMsg.activeTool = null; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onChainStart: () => { logger.debug("onChainStart"); },
        onHeartbeatRelayStart: ({ message: msg }) => {
          logger.debug(`onHeartbeatRelayStart: ${msg}`);
          streamingMsg.heartbeatRelay = true; streamingMsg.heartbeatText = "";
          ctx.controllers.renderer.renderStreamingBubble(streamingMsg);
          ctx.controllers.activity.addLocalActivity("system", name, `${t("chat.heartbeat_relay")}: ${msg}`);
        },
        onHeartbeatRelay: ({ text }) => {
          streamingMsg.heartbeatText = (streamingMsg.heartbeatText || "") + text;
          ctx.controllers.renderer.renderStreamingBubble(streamingMsg);
        },
        onHeartbeatRelayDone: () => {
          streamingMsg.heartbeatRelay = false; streamingMsg.heartbeatText = ""; streamingMsg.afterHeartbeatRelay = true;
          ctx.controllers.renderer.renderStreamingBubble(streamingMsg);
        },
        onThinkingStart: () => { streamingMsg.thinkingText = ""; streamingMsg.thinking = true; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onThinkingDelta: text => { streamingMsg.thinkingText = (streamingMsg.thinkingText || "") + text; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onThinkingEnd: () => { streamingMsg.thinking = false; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onError: ({ message: errorMsg }) => {
          logger.debug(`onError: ${errorMsg}`);
          streamingMsg.text += `\n${t("chat.error_prefix")} ${errorMsg}`;
          streamingMsg.streaming = false;
          ctx.controllers.renderer.renderChat();
        },
        onDone: ({ summary, images: doneImages }) => {
          const text = summary || streamingMsg.text;
          streamingMsg.text = text || t("chat.empty_response");
          streamingMsg.images = doneImages || [];
          streamingMsg.streaming = false;
          streamingMsg.activeTool = null;
          streamingMsg.heartbeatRelay = false; streamingMsg.heartbeatText = ""; streamingMsg.afterHeartbeatRelay = false;
          ctx.controllers.renderer.renderChat();
          ctx.controllers.activity.addLocalActivity("chat", name, `${t("chat.response_prefix")} ${streamingMsg.text.slice(0, 100)}`);
          ctx.controllers.renderer.markResponseComplete(name, tid);
        },
      });

      if (streamingMsg.streaming) {
        streamingMsg.streaming = false;
        if (!streamingMsg.text) {
          streamingMsg.text = streamingMsg.afterHeartbeatRelay ? t("chat.receive_failed") : t("chat.empty_response");
        }
        streamingMsg.afterHeartbeatRelay = false;
        ctx.controllers.renderer.renderChat();
      }
      sendSucceeded = true;

      const inputEl = $("chatPageInput");
      if (sendSucceeded && inputEl && inputEl.value.trim() === message.trim()) {
        inputEl.value = "";
        inputEl.style.height = "auto";
        clearDraft(name);
      }
    } catch (err) {
      if (err.name === "AbortError") {
        streamingMsg.streaming = false; streamingMsg.activeTool = null;
        if (!streamingMsg.text) streamingMsg.text = t("chat.interrupted");
        ctx.controllers.renderer.renderChat();
      } else {
        logger.error("Chat stream error", { anima: name, error: err.message, name: err.name });
        streamingMsg.text += `\n${t("chat.error_prefix")} ${err.message}`;
        streamingMsg.streaming = false; streamingMsg.activeTool = null;
        ctx.controllers.renderer.renderChat();
      }
    } finally {
      state.streamingContext = null;
      state.chatAbortController = null;
      const inputEl = $("chatPageInput");
      if (inputEl) {
        inputEl.placeholder = t("chat.message_to", { name });
        saveDraft(name, inputEl.value || "");
        inputEl.focus();
      }
      updateSendButton();
      ctx.controllers.anima.renderAnimaTabs();

      if (state.pendingQueue.length > 0) {
        const next = state.pendingQueue.shift();
        showPendingIndicator();
        if (state.pendingQueue.length === 0) hidePendingIndicator();
        setTimeout(() => sendChat(next.text, { images: next.images, displayImages: next.displayImages }), 150);
      }
    }
  }

  async function resumeActiveStream(animaName) {
    if (state.streamingContext || state.chatAbortController) return;
    try {
      const active = await fetchActiveStream(animaName);
      if (!active || active.status !== "streaming") return;
      const progress = await fetchStreamProgress(animaName, active.response_id);
      if (!progress) return;

      const tid = state.selectedThreadId || "default";
      if (!state.chatHistories[animaName]) state.chatHistories[animaName] = {};
      if (!state.chatHistories[animaName][tid]) state.chatHistories[animaName][tid] = [];
      const history = state.chatHistories[animaName][tid];

      const streamingMsg = {
        role: "assistant", text: progress.full_text || "", streaming: true,
        activeTool: progress.active_tool || null, timestamp: new Date().toISOString(),
        thinkingText: "", thinking: false,
      };
      history.push(streamingMsg);
      ctx.controllers.renderer.renderChat();

      state.streamingContext = { anima: animaName, thread: tid };
      state.chatAbortController = new AbortController();
      updateSendButton();
      ctx.controllers.anima.renderAnimaTabs();

      const currentUser = localStorage.getItem("animaworks_user") || "human";
      const resumeBody = JSON.stringify({
        message: "", from_person: currentUser,
        resume: active.response_id, last_event_id: progress.last_event_id || "",
      });

      await streamChat(animaName, resumeBody, state.chatAbortController.signal, {
        onTextDelta: text => { streamingMsg.text += text; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onToolStart: toolName => { streamingMsg.activeTool = toolName; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onToolEnd: () => { streamingMsg.activeTool = null; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onThinkingStart: () => { streamingMsg.thinkingText = ""; streamingMsg.thinking = true; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onThinkingDelta: text => { streamingMsg.thinkingText = (streamingMsg.thinkingText || "") + text; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onThinkingEnd: () => { streamingMsg.thinking = false; ctx.controllers.renderer.renderStreamingBubble(streamingMsg); },
        onError: ({ message: errorMsg }) => { streamingMsg.text += `\n${t("chat.error_prefix")} ${errorMsg}`; streamingMsg.streaming = false; ctx.controllers.renderer.renderChat(); },
        onDone: ({ summary, images }) => {
          streamingMsg.text = summary || streamingMsg.text || t("chat.empty_response");
          streamingMsg.images = images || [];
          streamingMsg.streaming = false; streamingMsg.activeTool = null;
          ctx.controllers.renderer.renderChat();
          ctx.controllers.renderer.markResponseComplete(animaName, tid);
        },
      });

      if (streamingMsg.streaming) {
        streamingMsg.streaming = false;
        if (!streamingMsg.text) streamingMsg.text = t("chat.empty_response");
        ctx.controllers.renderer.renderChat();
      }
    } catch (err) {
      if (err.name !== "AbortError") logger.error("Resume stream error", { anima: animaName, error: err.message });
    } finally {
      state.streamingContext = null;
      state.chatAbortController = null;
      updateSendButton();
      ctx.controllers.anima.renderAnimaTabs();
    }
  }

  return {
    submitChat, sendChat, resumeActiveStream,
    stopStreaming, addToQueue,
    showPendingIndicator, hidePendingIndicator,
    updateSendButton,
  };
}
