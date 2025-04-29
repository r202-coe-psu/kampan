function initDatePicker(buttonId, popoverId, inputId, buttonTextId) {
  const button = document.getElementById(buttonId);
  const popover = document.getElementById(popoverId);
  const input = document.getElementById(inputId);
  const buttonText = document.getElementById(buttonTextId);

  if (input.value) {
    buttonText.innerText = new Date(input.value).toLocaleDateString('en-GB');
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
    const start_date = new Date(start_input.value);
    const end_date = new Date(end_input.value);
    buttonText.innerText = `${start_date.toLocaleDateString('en-GB')} - ${end_date.toLocaleDateString('en-GB')}`;
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

