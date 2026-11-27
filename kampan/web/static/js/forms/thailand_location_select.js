// จังหวัด → อำเภอ → ตำบล แบบ dropdown ต่อกัน (macro thai_location_fields ใน base/html-renderer.html)
// เปลี่ยนชั้นบน → ล้างชั้นล่างทั้งหมด แล้วโหลดตัวเลือกของชั้นถัดไปจาก /api/thailand-location
// ใช้ฟังก์ชันของ dropdown_select.js (setDropdownSelectValue)
(function () {
  const NEXT = { province: "district", district: "subdistrict" };
  const URL_ATTR = { district: "districtsUrl", subdistrict: "subdistrictsUrl" };

  function levelOf(group, level) {
    const fieldset = group.querySelector('[data-level="' + level + '"]');
    if (!fieldset) return null;
    return {
      fieldset: fieldset,
      container: fieldset.querySelector("[data-dropdown-select]"),
      input: fieldset.querySelector("input[type=hidden]"),
      button: fieldset.querySelector("[data-dd-button]"),
      list: fieldset.querySelector("[data-dd-menu] ul"),
    };
  }

  function setOptions(part, names) {
    part.list.replaceChildren();
    names.forEach(function (name) {
      const li = document.createElement("li");
      li.className = "w-full";
      const option = document.createElement("button");
      option.type = "button";
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", "false");
      option.dataset.value = name;
      option.className = "w-full text-left justify-start";
      option.textContent = name;
      li.appendChild(option);
      part.list.appendChild(li);
    });
  }

  function setEnabled(part, enabled, placeholder) {
    part.input.disabled = !enabled;
    part.button.disabled = !enabled;
    part.container.dataset.placeholder = placeholder;
    setDropdownSelectValue(part.container, "", false);
  }

  function setLoading(part, loading) {
    const label = part.button.querySelector("[data-dd-label]");
    let spinner = part.button.querySelector(".loading");
    if (loading && !spinner) {
      spinner = document.createElement("span");
      spinner.className = "loading loading-spinner loading-xs shrink-0";
      part.button.appendChild(spinner);
    } else if (!loading && spinner) {
      spinner.remove();
    }
    if (loading) label.textContent = "กำลังโหลด...";
  }

  function clearBelow(group, level) {
    let below = NEXT[level];
    while (below) {
      const part = levelOf(group, below);
      if (!part) break;
      setOptions(part, []);
      setEnabled(part, false, part.fieldset.dataset.waitingText);
      below = NEXT[below];
    }
  }

  function load(group, level) {
    const next = NEXT[level];
    const part = next && levelOf(group, next);
    if (!part) return;
    const params = new URLSearchParams({ province: levelOf(group, "province").input.value });
    if (next === "subdistrict") params.set("district", levelOf(group, "district").input.value);
    const requestId = String((Number(group.dataset.requestId) || 0) + 1);
    group.dataset.requestId = requestId;
    setLoading(part, true);
    fetch(group.dataset[URL_ATTR[next]] + "?" + params, { credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error(response.status);
        return response.json();
      })
      .then(function (rows) {
        if (group.dataset.requestId !== requestId) return; // เลือกชั้นบนใหม่ระหว่างรอ
        const names = rows.map(function (row) { return typeof row === "string" ? row : row.subdistrict; });
        setOptions(part, names);
        setEnabled(part, true, "เลือก" + part.button.getAttribute("aria-label"));
      })
      .catch(function () {
        if (group.dataset.requestId !== requestId) return;
        setEnabled(part, false, "โหลดตัวเลือกไม่สำเร็จ ลองเลือกใหม่อีกครั้ง");
      })
      .finally(function () {
        if (group.dataset.requestId === requestId) setLoading(part, false);
      });
  }

  function initThaiLocationIn(root) {
    (root || document).querySelectorAll("[data-thai-location]").forEach(function (group) {
      if (group.dataset.thaiLocationInit) return;
      group.dataset.thaiLocationInit = "1";
      ["province", "district"].forEach(function (level) {
        const part = levelOf(group, level);
        if (!part) return;
        part.input.addEventListener("change", function () {
          clearBelow(group, level);
          if (part.input.value) load(group, level);
        });
      });
    });
  }

  window.initThaiLocationIn = initThaiLocationIn;
  document.addEventListener("DOMContentLoaded", function () { initThaiLocationIn(document); });
})();
