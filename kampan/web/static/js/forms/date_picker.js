// ปฏิทินเปิดชิดซ้ายของช่องเสมอ ถ้าช่องอยู่ทางขวาของจอ (เช่นคอลัมน์สุดท้ายของฟอร์มค้นหา)
// ปฏิทินสองเดือนจะล้นจอ จึงเลื่อนกลับเข้ามาให้อยู่ในจอทุกครั้งที่เปิด
const POPOVER_VIEWPORT_MARGIN = 8;

function keepPopoverInViewport(popover) {
  if (popover.classList.contains("hidden")) return;

  popover.style.left = "";
  popover.style.right = "";
  const rect = popover.getBoundingClientRect();
  const viewportWidth = document.documentElement.clientWidth;
  if (rect.right <= viewportWidth - POPOVER_VIEWPORT_MARGIN) return;

  const parentLeft = (popover.offsetParent || document.body).getBoundingClientRect().left;
  const targetLeft = Math.max(
    POPOVER_VIEWPORT_MARGIN,
    viewportWidth - POPOVER_VIEWPORT_MARGIN - rect.width
  );
  popover.style.left = `${targetLeft - parentLeft}px`;
  popover.style.right = "auto";
}

function initDatePicker(buttonId, popoverId, inputId, buttonTextId) {
  const button = document.getElementById(buttonId);
  const popover = document.getElementById(popoverId);
  const input = document.getElementById(inputId);
  const buttonText = document.getElementById(buttonTextId);

  if (input.value) {
    const parts = input.value.split('-');
    if (parts.length === 3) {
      buttonText.innerText = `${parts[2]}/${parts[1]}/${parts[0]}`;
    } else {
      buttonText.innerText = input.value;
    }
  }

  button.addEventListener("click", function () {
    popover.classList.toggle("hidden");
    keepPopoverInViewport(popover);
  });

  document.addEventListener("click", function (event) {
    if (!button.contains(event.target) && !popover.contains(event.target)) {
      popover.classList.add("hidden");
    }
  });
}

// ===== date picker แบบ data attribute (ใช้กับแถวที่เพิ่มด้วย JS ซึ่ง <script> ใน HTML ที่แทรกไม่ทำงาน) =====
function formatPickerDate(iso) {
  const parts = (iso || "").split("-");
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : iso || "";
}

// วางปฏิทินแบบ fixed ใต้ปุ่ม (ไม่ถูกตัดด้วย overflow-x-auto ของตาราง) ถ้าที่ล่างไม่พอให้ขึ้นด้านบน
function positionFixedPopover(button, popover) {
  if (popover.classList.contains("hidden")) return;
  const rect = button.getBoundingClientRect();
  const width = popover.offsetWidth;
  const height = popover.offsetHeight;
  const viewportWidth = document.documentElement.clientWidth;
  const viewportHeight = document.documentElement.clientHeight;
  let left = Math.min(rect.left, viewportWidth - POPOVER_VIEWPORT_MARGIN - width);
  left = Math.max(POPOVER_VIEWPORT_MARGIN, left);
  let top = rect.bottom + 4;
  if (top + height > viewportHeight - POPOVER_VIEWPORT_MARGIN && rect.top - 4 - height >= POPOVER_VIEWPORT_MARGIN) {
    top = rect.top - 4 - height;
  }
  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

// ตั้งค่า date picker ด้วยโค้ด: hidden input (ISO) + ข้อความบนปุ่ม (dd/mm/yyyy) + ปฏิทิน แล้วยิง change ที่ hidden input
function setDatePickerValue(input, iso) {
  const container = input.closest("[data-date-picker]");
  input.value = iso || "";
  if (container) {
    const label = document.getElementById(container.dataset.labelId);
    const calendar = container.querySelector("calendar-date");
    if (label) label.innerText = iso ? formatPickerDate(iso) : container.dataset.placeholder || "";
    if (calendar) calendar.value = iso || "";
    syncDatePickerClear(container);
  }
  input.dispatchEvent(new Event("change", { bubbles: true }));
}

function syncDatePickerClear(container) {
  const clear = container.querySelector("[data-date-clear]");
  const input = document.getElementById(container.dataset.inputId);
  if (clear && input) clear.classList.toggle("hidden", !input.value);
}

// เริ่มต้น date picker ทุกตัวใน root (เรียกซ้ำได้ ไม่ผูก event ซ้ำ)
function initDatePickersIn(root) {
  (root || document).querySelectorAll("[data-date-picker]").forEach(function (container) {
    if (container.dataset.dateInit) return;
    container.dataset.dateInit = "1";
    const { buttonId, popoverId, inputId, labelId } = container.dataset;
    const input = document.getElementById(inputId);
    const popover = document.getElementById(popoverId);
    const button = document.getElementById(buttonId);
    if (!input || !popover || !button) return;
    initDatePicker(buttonId, popoverId, inputId, labelId);

    const fixed = popover.classList.contains("fixed");
    if (fixed) {
      button.addEventListener("click", function () {
        positionFixedPopover(button, popover);
        requestAnimationFrame(function () { positionFixedPopover(button, popover); });
      });
      window.addEventListener("resize", function () { popover.classList.add("hidden"); });
      window.addEventListener("scroll", function (event) {
        if (!popover.contains(event.target)) popover.classList.add("hidden");
      }, true);
    }
    const calendar = popover.querySelector("calendar-date");
    if (calendar) calendar.addEventListener("change", function () { syncDatePickerClear(container); });
    const clear = container.querySelector("[data-date-clear]");
    if (clear) {
      clear.addEventListener("click", function () {
        setDatePickerValue(input, "");
        popover.classList.add("hidden");
      });
    }
    syncDatePickerClear(container);
  });
}

function initDateRange(buttonId, popoverId, startId, endId, buttonTextId) {
  const button = document.getElementById(buttonId);
  const popover = document.getElementById(popoverId);
  const start_input = document.getElementById(startId);
  const end_input = document.getElementById(endId);
  const buttonText = document.getElementById(buttonTextId);

  if (start_input.value && end_input.value) {
    const startParts = start_input.value.split('-');
    const endParts = end_input.value.split('-');
    const startStr = startParts.length === 3 ? `${startParts[2]}/${startParts[1]}/${startParts[0]}` : start_input.value;
    const endStr = endParts.length === 3 ? `${endParts[2]}/${endParts[1]}/${endParts[0]}` : end_input.value;
    buttonText.innerText = `${startStr} - ${endStr}`;
  }

  button.addEventListener("click", function () {
    popover.classList.toggle("hidden");
    keepPopoverInViewport(popover);
  });

  document.addEventListener("click", function (event) {
    if (!button.contains(event.target) && !popover.contains(event.target)) {
      popover.classList.add("hidden");
    }
  });
}

