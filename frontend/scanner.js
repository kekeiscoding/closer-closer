import { BrowserQRCodeReader } from "@zxing/browser";
import { DecodeHintType } from "@zxing/library";
import "./payments.js";

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
      const first = form.elements.namedItem("entry_from").value;
      const last = form.elements.namedItem("entry_to");
      last.min = /^\d{4}$/.test(first) ? first : "1900";
      form.elements.namedItem("graduation_date").min = /^\d{4}$/.test(last.value)
        ? last.value + "-01-01" : "";
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
  const picker = panel.querySelector("[data-camera-picker]");
  const cameras = panel.querySelector("[data-camera-select]");
  const devices = navigator.mediaDevices;
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
    if (mode === "order" && /^\/(checkout\/[A-Za-z0-9_-]{43}|pay\/IS-[A-F0-9]{12})$/.test(url.pathname)) {
      stop();
      location.assign(url.pathname);
      return true;
    }

    message(mode === "document" ? "Scan the QR printed on a Registrar PDF." : "Scan an order or payment QR.");
    return false;
  }

  async function listCameras(active, selected) {
    try {
      const choices = (await devices.enumerateDevices()).filter(
        (device) => device.kind === "videoinput" && device.deviceId,
      );
      if (active !== generation) return;
      cameras.replaceChildren(...choices.map((device, index) =>
        new Option(device.label || "Camera " + (index + 1), device.deviceId, false, device.deviceId === selected),
      ));
      picker.hidden = choices.length === 0;
    } catch {
      // A working camera can still scan when the browser restricts device listing.
    }
  }

  async function startCamera(deviceId) {
    stop();
    message("");
    if (!devices?.getUserMedia) {
      message("Camera access requires HTTPS or localhost. You can upload a QR image instead.");
      return;
    }
    const active = ++generation;
    preview.hidden = false;
    camera.disabled = true;
    try {
      const stream = await reader.decodeFromConstraints(
        { audio: false, video: deviceId ? { deviceId: { exact: deviceId } } : { facingMode: { ideal: "environment" } } },
        video,
        (result) => {
          if (result && active === generation) handle(result);
        },
      );
      if (active !== generation) {
        stream.stop();
        return;
      }
      controls = stream;
      await listCameras(active, video.srcObject?.getVideoTracks()[0]?.getSettings().deviceId || deviceId);
    } catch {
      if (active === generation) {
        stop();
        if (deviceId) {
          preview.hidden = false;
          await listCameras(generation);
        }
        message("Camera unavailable. Select another camera or upload a QR image.");
      }
    }
  }

  camera.addEventListener("click", () => startCamera());
  cameras.addEventListener("change", () => startCamera(cameras.value));
  devices?.addEventListener("devicechange", () => {
    if (!preview.hidden) listCameras(generation, cameras.value);
  });
  panel.querySelector("[data-scan-stop]").addEventListener("click", stop);
  upload.addEventListener("change", async () => {
    const file = upload.files[0];
    if (!file) return;
    stop();
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

function prepareHeroParallax(hero) {
  if (
    CSS.supports("(animation-timeline: view()) and (animation-range: entry)") ||
    matchMedia("(prefers-reduced-motion: reduce)").matches
  ) {
    return;
  }
  const header = document.querySelector(".site-header");
  let frame = 0;

  function update() {
    frame = 0;
    const rect = hero.getBoundingClientRect();
    const inset = header ? header.getBoundingClientRect().height : 0;
    const height = rect.height || 1;
    const shift = Math.max(0, Math.min(height, inset - rect.top));
    hero.style.setProperty("--hero-shift", `${shift}px`);
    hero.style.setProperty("--hero-progress", (shift / height).toFixed(4));
  }

  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        window.addEventListener("scroll", schedule, { passive: true });
        window.addEventListener("resize", schedule, { passive: true });
        schedule();
      } else {
        window.removeEventListener("scroll", schedule);
        window.removeEventListener("resize", schedule);
      }
    }
  }, { threshold: 0 });

  observer.observe(hero);
  update();
}

document.querySelectorAll(".form-stack[method=post]").forEach(prepareForm);
document.querySelectorAll("[data-scan-mode]").forEach(prepareScanner);
document.querySelectorAll("[data-hero-parallax]").forEach(prepareHeroParallax);
