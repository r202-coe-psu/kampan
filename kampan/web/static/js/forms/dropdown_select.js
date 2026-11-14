// DaisyUI dropdown แทน <select> (macro dropdown_select ใน base/html-renderer.html)
// hidden input เก็บค่า (name เดิม) · คลิก / คีย์บอร์ด (ลูกศร, Home, End, Enter, Space, Esc, ตัวอักษรแรก) · ปิดเมื่อคลิกนอก
function dropdownOptions(menu) {
  return Array.from(menu.querySelectorAll("[data-value]"));
}

function closeDropdownSelect(container, returnFocus) {
  const menu = container.querySelector("[data-dd-menu]");
  const button = container.querySelector("[data-dd-button]");
  menu.classList.add("hidden");
  button.setAttribute("aria-expanded", "false");
  if (returnFocus) button.focus();
}

function openDropdownSelect(container) {
  document.querySelectorAll("[data-dropdown-select]").forEach(function (other) {
    if (other !== container) closeDropdownSelect(other, false);
  });
  const menu = container.querySelector("[data-dd-menu]");
  const button = container.querySelector("[data-dd-button]");
  if (button.disabled) return;
  menu.classList.remove("hidden");
  button.setAttribute("aria-expanded", "true");
  // เมนูชิดล่างจอ: เปิดขึ้นด้านบนถ้าที่ล่างไม่พอ
  const rect = menu.getBoundingClientRect();
  const flip = rect.bottom > window.innerHeight && button.getBoundingClientRect().top > rect.height + 8;
  menu.classList.toggle("bottom-full", flip);
  menu.classList.toggle("mb-1", flip);
  menu.classList.toggle("top-full", !flip);
  menu.classList.toggle("mt-1", !flip);
  const options = dropdownOptions(menu);
  const searchInput = menu.querySelector(".dd-search-input");
  if (searchInput) {
    searchInput.value = "";
    dropdownOptions(menu).forEach(function (opt) {
      const li = opt.closest("li");
      if (li) li.classList.remove("hidden");
    });
    setTimeout(function () { searchInput.focus(); }, 30);
  } else {
    const selected = options.find(function (option) { return option.getAttribute("aria-selected") === "true"; });
    if (selected || options[0]) (selected || options[0]).focus();
  }
}

function setDropdownSelectValue(container, value, notify) {
  const input = container.querySelector("input[type=hidden]");
  const label = container.querySelector("[data-dd-label]");
  let text = "";
  dropdownOptions(container).forEach(function (option) {
    const isSelected = option.dataset.value === value;
    option.setAttribute("aria-selected", isSelected ? "true" : "false");
    option.classList.toggle("menu-active", isSelected);
    if (isSelected) text = option.textContent.trim();
  });
  input.value = value;
  label.textContent = text || container.dataset.placeholder || "";
  label.classList.toggle("text-base-content/50", !text);
  if (notify) {
    input.dispatchEvent(new Event("change", { bubbles: true }));
    if (container.hasAttribute("data-submit-on-change") && input.form) input.form.requestSubmit();
  }
}

function initDropdownSelectsIn(root) {
  (root || document).querySelectorAll("[data-dropdown-select]").forEach(function (container) {
    if (container.dataset.ddInit) return;
    container.dataset.ddInit = "1";
    const button = container.querySelector("[data-dd-button]");
    const menu = container.querySelector("[data-dd-menu]");

    const searchInput = menu.querySelector(".dd-search-input");
    if (searchInput) {
      searchInput.addEventListener("input", function () {
        const query = searchInput.value.trim().toLowerCase();
        dropdownOptions(menu).forEach(function (option) {
          const match = !query || option.textContent.toLowerCase().includes(query);
          const li = option.closest("li");
          if (li) li.classList.toggle("hidden", !match);
        });
      });
      searchInput.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          closeDropdownSelect(container, true);
        } else if (e.key === "ArrowDown") {
          e.preventDefault();
          const visible = dropdownOptions(menu).filter(function (opt) {
            const li = opt.closest("li");
            return !li || !li.classList.contains("hidden");
          });
          if (visible.length) visible[0].focus();
        }
      });
    }

    button.addEventListener("click", function () {
      if (menu.classList.contains("hidden")) openDropdownSelect(container);
      else closeDropdownSelect(container, false);
    });
    button.addEventListener("keydown", function (event) {
      if (["ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault();
        openDropdownSelect(container);
      }
    });
    menu.addEventListener("click", function (event) {
      const option = event.target.closest("[data-value]");
      if (!option) return;
      setDropdownSelectValue(container, option.dataset.value, true);
      closeDropdownSelect(container, true);
    });
    menu.addEventListener("keydown", function (event) {
      const options = dropdownOptions(menu);
      const index = options.indexOf(document.activeElement);
      const move = function (target) { event.preventDefault(); options[(target + options.length) % options.length].focus(); };
      if (event.key === "ArrowDown") move(index + 1);
      else if (event.key === "ArrowUp") move(index - 1);
      else if (event.key === "Home") move(0);
      else if (event.key === "End") move(options.length - 1);
      else if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeDropdownSelect(container, true);
      } else if (event.key === "Tab") closeDropdownSelect(container, false);
      else if (event.key.length === 1 && /\S/.test(event.key)) {
        const typed = event.key.toLowerCase();
        const ordered = options.slice(index + 1).concat(options.slice(0, index + 1));
        const match = ordered.find(function (option) { return option.textContent.trim().toLowerCase().startsWith(typed); });
        if (match) match.focus();
      }
    });
  });
}

document.addEventListener("click", function (event) {
  document.querySelectorAll("[data-dropdown-select]").forEach(function (container) {
    if (!container.contains(event.target)) closeDropdownSelect(container, false);
  });
});
document.addEventListener("DOMContentLoaded", function () { initDropdownSelectsIn(document); });
