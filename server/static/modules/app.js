/* ============================================
   AnimaWorks — Dashboard App (Entry Point)
   ============================================ */

import { state } from "./state.js";
import { connectWebSocket } from "./websocket.js";
import { loadSystemStatus } from "./status.js";
import { loginAs, logout, showLoginScreen, hideLoginScreen, setStartDashboard } from "./login.js";
import { initRouter } from "./router.js";

// ── Dashboard Startup ───────────────────────

async function startDashboard() {
  initRouter("pageContent");
  connectWebSocket();
  loadSystemStatus();
}

setStartDashboard(startDashboard);

// ── Mobile Navigation ────────────────────────

function initMobileNav() {
  const hamburgerBtn = document.getElementById("hamburgerBtn");
  const backdrop = document.getElementById("mobileNavBackdrop");
  const sidebarNav = document.getElementById("sidebarNav");

  function openNav() {
    document.body.classList.add("mobile-nav-open");
  }

  function closeNav() {
    document.body.classList.remove("mobile-nav-open");
  }

  if (hamburgerBtn) {
    hamburgerBtn.addEventListener("click", () => {
      if (document.body.classList.contains("mobile-nav-open")) {
        closeNav();
      } else {
        openNav();
      }
    });
  }

  if (backdrop) {
    backdrop.addEventListener("click", closeNav);
  }

  // Close on nav item click
  if (sidebarNav) {
    sidebarNav.addEventListener("click", (e) => {
      if (e.target.closest(".nav-item")) {
        closeNav();
      }
    });
  }
}

// ── Init ────────────────────────────────────

async function init() {
  // Login/logout bindings
  document.getElementById("guestLoginBtn").addEventListener("click", () => loginAs("human"));
  document.getElementById("logoutBtn").addEventListener("click", logout);

  // Mobile navigation
  initMobileNav();

  if (state.currentUser) {
    hideLoginScreen();
    await startDashboard();
  } else {
    showLoginScreen();
  }

  // Periodic refresh: system status every 60s
  setInterval(loadSystemStatus, 60000);
}

// Start when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
