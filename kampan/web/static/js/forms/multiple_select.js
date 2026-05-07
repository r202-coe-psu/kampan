document.addEventListener("DOMContentLoaded", function () {
    // หาองค์ประกอบทั้งหมดที่เป็น multi-select
    const multiSelectContainers = document.querySelectorAll("[id$='multiSelectContainer']");

    multiSelectContainers.forEach(function (container) {
        const id_prefix = container.id.replace('multiSelectContainer', '');

        // ดึงข้อมูลที่จำเป็น
        const optionsData = document.getElementById(`${id_prefix}options`);
        const selectedData = document.getElementById(`${id_prefix}selectedData`);
        const options = JSON.parse(optionsData.textContent);
        const selected = new Set(JSON.parse(selectedData.textContent));

        const input = document.getElementById(`${id_prefix}${optionsData.getAttribute('data-field-name')}`);
        const searchInput = document.getElementById(`${id_prefix}searchInput`);
        const dropdown = document.getElementById(`${id_prefix}dropdown`);
        const selectedItems = document.getElementById(`${id_prefix}selectedItems`);
        const multiSelectBox = document.getElementById(`${id_prefix}multiSelectBox`);

        // ฟังก์ชันภายในสำหรับจัดการแต่ละฟิลด์
        function updateSelectedItems() {
            selectedItems.innerHTML = "";
            selected.forEach(id => {
                const option = options.find(option => option[0] === id);
                if (option) {
                    const span = document.createElement("div");
                    span.className = "badge badge-primary h-auto py-1 px-3 gap-2";
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "hover:text-error transition-colors";
                    button.innerHTML = '<i class="ph ph-x-circle text-lg"></i>';
                    button.onclick = function (e) { 
                        e.stopPropagation();
                        removeSelection(id); 
                    };
                    const textNode = document.createTextNode(option[1]);
                    span.appendChild(textNode);
                    span.appendChild(button);
                    selectedItems.appendChild(span);
                }
            });
            Array.from(input.options).forEach(option => {
                option.selected = selected.has(option.value);
            });
        }

        function updateDropdown() {
            dropdown.innerHTML = "";
            const searchTerm = searchInput.value.toLowerCase();
            const filteredOptions = options.filter(option => option[1].toLowerCase().includes(searchTerm));

            if (filteredOptions.length === 0) {
                const li = document.createElement("li");
                li.className = "px-4 text-gray-500 py-2";
                li.textContent = "ไม่พบข้อมูล";
                dropdown.appendChild(li);
            } else {
                filteredOptions.forEach(option => {
                    const li = document.createElement("li");
                    li.className = `px-4 py-2 cursor-pointer transition-colors border-b border-base-200 last:border-0 ${selected.has(option[0]) ? 'bg-primary text-primary-content' : 'hover:bg-base-200'}`;
                    li.textContent = option[1];
                    li.onclick = () => toggleSelection(option[0]);
                    dropdown.appendChild(li);
                });
            }
        }

        function toggleSelection(id) {
            if (selected.has(id)) {
                selected.delete(id);
            } else {
                selected.add(id);
            }
            updateSelectedItems();
            updateDropdown();
        }

        function removeSelection(id) {
            selected.delete(id);
            updateSelectedItems();
            updateDropdown();
        }

        searchInput.addEventListener("input", updateDropdown);
        multiSelectBox.addEventListener("click", () => {
            dropdown.classList.toggle("hidden");
            updateDropdown();
        });
        document.addEventListener("click", event => {
            if (!container.contains(event.target)) {
                dropdown.classList.add("hidden");
            }
        });

        // เรียกใช้ฟังก์ชันเริ่มต้น
        updateSelectedItems();
    });
});
