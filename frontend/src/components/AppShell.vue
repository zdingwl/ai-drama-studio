<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand-lockup">
        <span class="brand-mark" aria-hidden="true">AI</span>
        <div>
          <strong>AI Drama Studio</strong>
          <small>用 AI 让好故事走向全世界</small>
        </div>
      </div>
      <div class="header-actions">
        <span class="header-icon" aria-hidden="true">?</span>
        <span class="header-icon" aria-hidden="true">⚙</span>
        <span>简体中文⌄</span>
      </div>
    </header>
    <main class="app-main">
      <slot />
    </main>
  </div>
</template>
