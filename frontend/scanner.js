import { BrowserQRCodeReader } from "@zxing/browser";
import { DecodeHintType } from "@zxing/library";

function prepareForm(form) {
  const conditional = form.querySelectorAll("[data-show-when]");
  const total = form.querySelector("[data-request-total]");
  const currency = new Intl.NumberFormat("en-PH", { style: "currency", currency: "PHP" });

  function activeValues(name) {
    return Array.from(form.elements)
      .filter((input) => input.name === name && !input.disabled && (input.type !== "checkbox" || input.checked))
      .map((input) => input.value);
  }

  function update() {
    for (const element of conditional) {
      const [name, expected] = element.dataset.showWhen.split(":");
      const values = activeValues(name);
      const visible = expected.startsWith("!")
        ? values.some((value) => value !== expected.slice(1))
        : values.includes(expected);
      element.hidden = !visible;
      for (const input of element.querySelectorAll("input, select, textarea")) {
        input.disabled = !visible;
      }
    }
    if (form.hasAttribute("data-registrar-form")) {
      const quantity = activeValues("services").reduce((sum, code) => {
        const number = form.elements.namedItem("copies_" + code).valueAsNumber;
        return sum + (number >= 1 && number <= 20 ? number : 0);
      }, 0);
      total.textContent = currency.format(quantity * Number(form.dataset.unitPrice) / 100);
    }
  }

  form.addEventListener("input", update);
  form.addEventListener("change", update);
  update();
}

async function readQrImage(reader, imageUrl, mode) {
  const image = new Image();
  image.src = imageUrl;
  await image.decode();
  try {
    return await reader.decodeFromImageElement(image);
  } catch {
    if (mode === "order") {
      const standalone = new BrowserQRCodeReader(new Map([[DecodeHintType.PURE_BARCODE, true]]));
      return standalone.decodeFromImageElement(image);
    }
  }
  // Registrar PDFs place the QR at the bottom right of the first page.
  const left = Math.floor(image.naturalWidth * .55);
  const top = Math.floor(image.naturalHeight * .62);
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth - left;
  canvas.height = image.naturalHeight - top;
  canvas.getContext("2d").drawImage(image, -left, -top);
  return reader.decodeFromCanvas(canvas);
}

function prepareScanner(panel) {
  const mode = panel.dataset.scanMode;
  const reader = new BrowserQRCodeReader(new Map([[DecodeHintType.TRY_HARDER, true]]));
  const camera = panel.querySelector("[data-scan-camera]");
  const preview = panel.querySelector("[data-scan-view]");
  const video = panel.querySelector("[data-scan-video]");
  const upload = panel.querySelector("[data-scan-file]");
  const status = panel.querySelector("[data-scan-status]");
  const link = panel.querySelector("[data-scan-link]");
  const supportedOrigin = new URL(panel.dataset.baseUrl).origin;
  let controls;
  let generation = 0;

  function message(text) {
    status.textContent = text;
    status.hidden = !text;
  }

  function stop() {
    generation++;
    controls?.stop();
    controls = undefined;
    preview.hidden = true;
    camera.disabled = false;
  }

  function handle(result) {
    let url;
    try {
      url = new URL(result.getText());
    } catch {
      message("This code is missing an ISATU - SSS link.");
      return false;
    }
    if (url.origin !== supportedOrigin && url.origin !== location.origin) {
      message("Choose an ISATU - SSS QR code.");
      return false;
    }

    if (mode === "document" && /^\/verify\/DOC-[A-F0-9]{16}$/.test(url.pathname)) {
      stop();
      location.assign(url.pathname);
      return true;
    }
    if (mode === "order" && url.pathname === "/cashier" && /^IS-[A-F0-9]{12}$/.test(url.searchParams.get("order_id") || "")) {
      stop();
      location.assign(url.pathname + url.search);
      return true;
    }
    if (mode === "order" && /^\/pay\/IS-[A-F0-9]{12}$/.test(url.pathname)) {
      stop();
      link.href = url.pathname;
      link.target = "_blank";
      link.rel = "noopener";
      link.hidden = false;
      message("The payment QR is ready to open in a new tab.");
      const checkoutTab = window.open(url.pathname, "_blank");
      if (checkoutTab) checkoutTab.opener = null;
      return true;
    }

    message(mode === "document" ? "Scan the QR printed on a Registrar PDF." : "Scan an order or payment QR.");
    return false;
  }

  camera.addEventListener("click", async () => {
    link.hidden = true;
    message("");
    if (!navigator.mediaDevices?.getUserMedia) {
      message("Camera access requires HTTPS or localhost. You can upload a QR image instead.");
      return;
    }
    const active = ++generation;
    preview.hidden = false;
    camera.disabled = true;
    try {
      const stream = await reader.decodeFromConstraints(
        { audio: false, video: { facingMode: { ideal: "environment" } } },
        video,
        (result) => {
          if (result && active === generation) handle(result);
        },
      );
      if (active === generation) controls = stream;
      else stream.stop();
    } catch {
      if (active === generation) {
        stop();
        message("Camera unavailable. Allow camera access or upload a QR image.");
      }
    }
  });

  panel.querySelector("[data-scan-stop]").addEventListener("click", stop);
  upload.addEventListener("change", async () => {
    const file = upload.files[0];
    if (!file) return;
    stop();
    link.hidden = true;
    message("Reading the QR image…");
    const imageUrl = URL.createObjectURL(file);
    try {
      handle(await readQrImage(reader, imageUrl, mode));
    } catch {
      message("The QR could not be read. Try a clear image of the entire code.");
    } finally {
      URL.revokeObjectURL(imageUrl);
      upload.value = "";
    }
  });
  window.addEventListener("pagehide", stop);
}

document.querySelectorAll(".form-stack[method=post]").forEach(prepareForm);
document.querySelectorAll("[data-scan-mode]").forEach(prepareScanner);
