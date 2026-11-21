function watchStatus(statusUrl, showStatus) {
  let socket;
  let retry;
  let polling;
  let ended = false;
  const live = new URL(statusUrl + "/live", location.href);
  live.protocol = location.protocol === "https:" ? "wss:" : "ws:";

  function stop() {
    ended = true;
    clearTimeout(retry);
    clearInterval(polling);
    socket?.close();
  }

  async function checkStatus() {
    if (ended || socket?.readyState === WebSocket.OPEN) return;
    try {
      const response = await fetch(statusUrl, { cache: "no-store" });
      if (response.status === 401 || response.status === 404) stop();
      if (response.ok) showStatus(await response.json(), stop);
    } catch {
      // The socket and polling retry when the connection returns.
    }
  }

  function connect() {
    if (ended) return;
    socket = new WebSocket(live);
    socket.addEventListener("message", (event) => showStatus(JSON.parse(event.data), stop));
    socket.addEventListener("close", () => {
      if (!ended) retry = setTimeout(connect, 1800);
    });
  }

  connect();
  polling = setInterval(checkStatus, 4000);
  window.addEventListener("pagehide", () => socket?.close());
}

function watchRequestViews() {
  const regions = Array.from(document.querySelectorAll("[data-payment-content]"));
  const pending = () => Array.from(document.querySelectorAll("[data-payment-order]"))
    .map((element) => element.dataset.paymentOrder);
  let updating = false;
  if (!regions.length || !pending().length) return;

  async function refresh({ paid_orders: paid }, stop) {
    if (updating || !pending().some((id) => paid.includes(id))) return;
    updating = true;
    try {
      const response = await fetch(location.href, { cache: "no-store" });
      if (response.redirected) {
        stop();
        return;
      }
      if (!response.ok) throw new Error("Could not fetch the updated requests.");
      const updated = new DOMParser().parseFromString(await response.text(), "text/html");
      for (const region of regions) {
        const next = updated.querySelector('[data-payment-content="' + region.dataset.paymentContent + '"]');
        if (!next) continue;
        region.replaceChildren(...next.childNodes);
        if (!next.dataset.paymentOrder) delete region.dataset.paymentOrder;
      }
      const notice = document.querySelector("[data-payment-notice]");
      if (notice) notice.textContent = "Payment status updated.";
      if (!pending().length) stop();
    } catch {
      setTimeout(() => refresh({ paid_orders: paid }, stop), 2000);
    } finally {
      updating = false;
    }
  }
  watchStatus("/payments/status", refresh);
}

function prepareGuestCheckout(section) {
  const form = section.querySelector("[data-guest-pay]");
  const button = form.querySelector("button");
  const normalLabel = button.textContent;
  const error = form.querySelector("[data-guest-error]");
  const success = section.querySelector("[data-guest-success]");

  function complete() {
    form.hidden = true;
    success.hidden = false;
    section.querySelector("[data-payment-heading]").textContent = "Payment complete";
  }

  watchStatus(section.dataset.statusUrl, ({ paid }, stop) => {
    if (paid) {
      complete();
      stop();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    button.textContent = "Processing…";
    error.hidden = true;
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        error.textContent = response.status === 409
          ? "This order’s academic dates need review before payment."
          : "Payment could not be recorded. Try again.";
        error.hidden = false;
        return;
      }
      complete();
    } catch {
      error.textContent = "Connection lost. Check the payment status before trying again.";
      error.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = normalLabel;
    }
  });
}

watchRequestViews();
const guest = document.querySelector("[data-guest-checkout][data-status-url]");
if (guest) prepareGuestCheckout(guest);
