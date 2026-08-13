/**
 * Three routes do not need a dependency.
 *
 * The History API plus one rune is the whole router, and it makes the seam the
 * agent uses explicit: `navigate()` is what the chat element calls, and it is the
 * same function the header buttons call. That is the single thing separating a
 * single-page host from a multi-page one — with it, a run continues across a view
 * change; without it, navigation reloads and the run is checkpointed instead.
 */

class Router {
  path = $state(window.location.pathname === "/" ? "/week" : window.location.pathname);

  constructor() {
    window.addEventListener("popstate", () => {
      this.path = window.location.pathname;
    });
    if (window.location.pathname === "/") {
      window.history.replaceState({}, "", "/week");
    }
  }

  navigate(path: string): void {
    if (path !== this.path) {
      window.history.pushState({}, "", path);
      this.path = path;
    }
  }
}

export const router = new Router();
