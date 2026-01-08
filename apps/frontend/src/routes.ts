// Simple routing utility using browser History API

export function getCurrentPath(): string {
  return window.location.pathname;
}

export function navigateTo(path: string) {
  window.history.pushState({}, '', path);
  // Dispatch a custom event to notify components of route change
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function initRouter(onRouteChange: (path: string) => void) {
  // Handle initial route
  onRouteChange(getCurrentPath());
  
  // Handle browser back/forward buttons and programmatic navigation
  window.addEventListener('popstate', () => {
    onRouteChange(getCurrentPath());
  });
}

