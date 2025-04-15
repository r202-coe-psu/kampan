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
                    const span = document.createElement("span");
                    span.className = "bg-blue-500 text-white px-2 py-1 rounded-lg flex items-center";
                    const button = document.createElement("button");
                    button.type = "button";
                    button.className = "ml-2 text-white";
                    button.textContent = "✕";
                    button.onclick = function () { removeSelection(id); };
                    span.textContent = option[1] + " ";
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
                    li.className = `px-4 py-1 cursor-pointer ${selected.has(option[0]) ? 'bg-blue-500 text-white' : 'hover:bg-gray-300 hover:text-black'}`;
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
