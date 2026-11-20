// ตัวเลือกเวลาแทนช่อง <input type="time"> ของเบราว์เซอร์ (หน้าตาต่างกันทุกเบราว์เซอร์และเลือกยากบนเดสก์ท็อป)
//
// ช่องเดิมยังเป็นช่องที่ฟอร์มส่งค่า (HH:MM ตามที่ WTForms TimeField อ่าน) แค่เปลี่ยนเป็นช่องข้อความ
// แล้วต่อ popover เลือกชั่วโมง/นาทีไว้ใต้ช่อง ไม่มี JS ก็ยังเป็นช่องเวลาปกติ
// พิมพ์เองได้: "930", "9.30", "9:3" จะถูกจัดเป็น 09:30 ตอนออกจากช่อง
(function () {
  const MINUTE_STEP = 5;
  const TIME_PATTERN = "([01][0-9]|2[0-3]):[0-5][0-9]";

  function pad(number) {
    return String(number).padStart(2, "0");
  }

  // แปลงข้อความที่พิมพ์เป็น "HH:MM" ถ้าอ่านไม่ออกคืน null
  function normalize(text) {
    const value = (text || "").trim();
    if (!value) return "";
    let hours;
    let minutes;
    const parts = value.split(/[:.\s]/).filter(Boolean);
    if (parts.length >= 2) {
      hours = Number(parts[0]);
      minutes = Number(parts[1].length === 1 ? parts[1] + "0" : parts[1]);
    } else if (/^\d{1,4}$/.test(value)) {
      const digits = value.length <= 2 ? value + "00" : value.padStart(4, "0");
      hours = Number(digits.slice(0, 2));
      minutes = Number(digits.slice(2));
    } else {
      return null;
    }
    if (!(hours >= 0 && hours <= 23 && minutes >= 0 && minutes <= 59)) return null;
    return `${pad(hours)}:${pad(minutes)}`;
  }

  function optionButton(label, value, kind) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-ghost btn-sm w-full justify-center tabular-nums";
    button.tabIndex = -1; // เลือกด้วยเมาส์/นิ้ว ส่วนคีย์บอร์ดพิมพ์เวลาในช่อง
    button.textContent = label;
    button.dataset.value = value;
    button.dataset.kind = kind;
    return button;
  }

  function column(title, items, kind) {
    const wrapper = document.createElement("div");
    wrapper.className = "flex w-20 flex-col";
    const heading = document.createElement("p");
    heading.className = "pb-1 text-center text-xs text-base-content/60";
    heading.textContent = title;
    const list = document.createElement("div");
    list.className = "flex max-h-56 flex-col gap-0.5 overflow-y-auto pr-1";
    list.dataset.column = kind;
    list.tabIndex = -1; // Chrome ให้กล่องที่เลื่อนได้รับโฟกัสจาก Tab ด้วย
    items.forEach((value) => list.appendChild(optionButton(pad(value), pad(value), kind)));
    wrapper.append(heading, list);
    return wrapper;
  }

  function enhance(input) {
    if (input.dataset.timePicker) return;
    input.dataset.timePicker = "on";

    const initial = normalize(input.value) || "";
    input.type = "text";
    input.value = initial;
    input.inputMode = "numeric";
    input.autocomplete = "off";
    input.maxLength = 5;
    input.placeholder = input.placeholder || "--:--";
    input.pattern = TIME_PATTERN;
    input.title = "เวลาแบบ 24 ชั่วโมง เช่น 08:30";
    input.classList.add("tabular-nums");

    const host = input.closest("label") || input.parentElement;
    const anchor = host.parentElement;
    anchor.classList.add("relative");

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "btn btn-ghost btn-xs btn-square -mr-1";
    toggle.setAttribute("aria-label", "เลือกเวลา");
    toggle.tabIndex = -1; // คีย์บอร์ดพิมพ์เวลาได้เลย กด Tab แล้วให้ออกจากช่องไปเลย
    toggle.setAttribute("aria-expanded", "false");
    toggle.innerHTML = '<i class="ph ph-clock text-lg"></i>';
    host.appendChild(toggle);

    const popover = document.createElement("div");
    popover.className =
      "absolute left-0 top-full z-5 mt-1 hidden rounded-box border border-base-300 bg-base-100 p-2 shadow-lg";
    popover.dataset.role = "time-picker";
    const hours = Array.from({ length: 24 }, (_, i) => i);
    const minutes = Array.from({ length: 60 / MINUTE_STEP }, (_, i) => i * MINUTE_STEP);
    const columns = document.createElement("div");
    columns.className = "flex gap-2";
    columns.append(column("ชั่วโมง", hours, "hour"), column("นาที", minutes, "minute"));
    popover.appendChild(columns);
    anchor.appendChild(popover);

    function current() {
      const value = normalize(input.value);
      if (!value) return { hour: null, minute: null };
      const [hour, minute] = value.split(":");
      return { hour, minute };
    }

    function highlight() {
      const { hour, minute } = current();
      popover.querySelectorAll("button[data-kind]").forEach((button) => {
        const selected =
          (button.dataset.kind === "hour" && button.dataset.value === hour) ||
          (button.dataset.kind === "minute" && button.dataset.value === minute);
        button.classList.toggle("btn-primary", selected);
        button.classList.toggle("btn-ghost", !selected);
        button.setAttribute("aria-pressed", selected ? "true" : "false");
      });
    }

    function scrollToSelected() {
      popover.querySelectorAll("[data-column]").forEach((list) => {
        const selected = list.querySelector(".btn-primary");
        if (selected) list.scrollTop = selected.offsetTop - list.offsetTop - list.clientHeight / 2 + selected.offsetHeight / 2;
      });
    }

    function open() {
      if (!popover.classList.contains("hidden")) return;
      popover.classList.remove("hidden");
      toggle.setAttribute("aria-expanded", "true");
      highlight();
      scrollToSelected();
    }

    function close() {
      popover.classList.add("hidden");
      toggle.setAttribute("aria-expanded", "false");
    }

    function setValue(value) {
      if (input.value === value) return;
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }

    // ปุ่มนาฬิกาอยู่ใน <label> คลิกแล้วช่องได้โฟกัส (เปิด popover) อยู่แล้ว จึงสั่งเปิดอย่างเดียว ไม่สลับปิด
    toggle.addEventListener("click", (event) => {
      event.preventDefault();
      input.focus();
      open();
    });
    input.addEventListener("focus", open);
    input.addEventListener("click", open);

    popover.addEventListener("mousedown", (event) => event.preventDefault()); // คงโฟกัสไว้ที่ช่อง
    popover.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-kind]");
      if (!button) return;
      const { hour, minute } = current();
      if (button.dataset.kind === "hour") {
        setValue(`${button.dataset.value}:${minute || "00"}`);
        highlight();
      } else {
        setValue(`${hour || "08"}:${button.dataset.value}`);
        close();
      }
    });

    input.addEventListener("blur", (event) => {
      const value = normalize(input.value);
      if (value !== null) setValue(value);
      if (!anchor.contains(event.relatedTarget)) close(); // กด Tab ออกจากช่อง
    });
    input.addEventListener("input", highlight);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });

    document.addEventListener("click", (event) => {
      if (!anchor.contains(event.target)) close();
    });
  }

  function enhanceAll(root) {
    (root || document).querySelectorAll('input[type="time"]').forEach(enhance);
  }

  window.kampanTimePicker = { enhanceAll, normalize };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => enhanceAll());
  } else {
    enhanceAll();
  }
  // ฟอร์มที่ htmx โหลดเข้ามาทีหลัง
  document.addEventListener("htmx:afterSwap", (event) => enhanceAll(event.target));
})();
