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
  });

  document.addEventListener("click", function (event) {
    if (!button.contains(event.target) && !popover.contains(event.target)) {
      popover.classList.add("hidden");
    }
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
  });

  document.addEventListener("click", function (event) {
    if (!button.contains(event.target) && !popover.contains(event.target)) {
      popover.classList.add("hidden");
    }
  });
}

