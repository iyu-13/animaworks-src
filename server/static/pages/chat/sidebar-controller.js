// ── Sidebar / Tab Switching Controller ─────────
import { $ } from "./ctx.js";

export function createSidebarController(ctx) {
  const { state, deps } = ctx;
  const { t } = deps;

  function switchMobileTab(panel) {
    const chatTab = $("chatMobileTabChat");
    const infoTab = $("chatMobileTabInfo");
    const mainPanel = state.container?.querySelector(".chat-page-main");
    const sidePanel = state.container?.querySelector(".chat-page-sidebar");
    if (!mainPanel || !sidePanel) return;

    if (panel === "chat") {
      chatTab?.classList.add("active");
      infoTab?.classList.remove("active");
      mainPanel.classList.remove("mobile-hidden");
      sidePanel.classList.add("mobile-hidden");
    } else {
      chatTab?.classList.remove("active");
      infoTab?.classList.add("active");
      mainPanel.classList.add("mobile-hidden");
      sidePanel.classList.remove("mobile-hidden");
    }
  }

  function switchRightTab(tab) {
    state.activeRightTab = tab;
    const tabs = { state: "chatPaneState", activity: "chatPaneActivity", history: "chatPaneHistory" };

    for (const btn of (state.container?.querySelectorAll(".right-tab") || [])) {
      btn.classList.toggle("active", btn.dataset.tab === tab);
    }
    for (const [key, id] of Object.entries(tabs)) {
      const el = $(id);
      if (el) el.style.display = key === tab ? "" : "none";
    }

    if (tab === "history" && state.selectedAnima) {
      const detail = $("chatHistoryDetail");
      const list = $("chatHistorySessionList");
      if (detail) detail.style.display = "none";
      if (list) list.style.display = "";
      ctx.controllers.history.loadSessionList();
    }
    if (tab === "activity") ctx.controllers.activity.loadActivity();
  }

  return { switchMobileTab, switchRightTab };
}
