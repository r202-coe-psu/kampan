// กล่องลากไฟล์มาวาง ([data-dropzone]) จาก macro FileDropzone
// ไฟล์ที่ลากมาวางถูกใส่กลับเข้า <input type="file"> ตัวจริง ฟอร์มจึงส่งแบบ multipart ตามปกติ
(function () {
  function formatMb(bytes) {
    return (bytes / 1024 / 1024).toFixed(0) + ' MB';
  }

  function setup(zone) {
    var input = zone.querySelector('input[type="file"]');
    var empty = zone.querySelector('[data-dropzone-empty]');
    var filled = zone.querySelector('[data-dropzone-filled]');
    var preview = zone.querySelector('[data-dropzone-preview]');
    var nameEl = zone.querySelector('[data-dropzone-name]');
    var errorEl = zone.querySelector('[data-dropzone-error]');
    var accept = (zone.dataset.accept || '').split(',').filter(Boolean);
    var maxBytes = parseInt(zone.dataset.maxBytes || '0', 10);
    var form = zone.closest('form');
    var submit = form && form.querySelector('[type="submit"]');

    function showError(message) {
      errorEl.textContent = message;
      errorEl.classList.toggle('hidden', !message);
      zone.classList.toggle('border-error', !!message);
    }

    function check(file) {
      if (accept.length && accept.indexOf(file.type) === -1) return 'ไฟล์ที่เลือกไม่ใช่รูปภาพ JPEG หรือ PNG';
      if (maxBytes && file.size > maxBytes) return 'ไฟล์ต้องมีขนาดไม่เกิน ' + formatMb(maxBytes);
      return '';
    }

    function render() {
      var file = input.files && input.files[0];
      if (!file) {
        empty.classList.remove('hidden');
        filled.classList.add('hidden');
        filled.classList.remove('flex');
        if (submit) submit.disabled = true;
        return;
      }
      var problem = check(file);
      showError(problem);
      if (submit) submit.disabled = !!problem;
      if (problem) {
        input.value = '';
        empty.classList.remove('hidden');
        filled.classList.add('hidden');
        filled.classList.remove('flex');
        return;
      }
      nameEl.textContent = file.name;
      if (preview.src) URL.revokeObjectURL(preview.src);
      preview.src = URL.createObjectURL(file);
      empty.classList.add('hidden');
      filled.classList.remove('hidden');
      filled.classList.add('flex');
    }

    ['dragenter', 'dragover'].forEach(function (type) {
      zone.addEventListener(type, function (event) {
        event.preventDefault();
        zone.classList.add('border-primary', 'bg-primary/10');
      });
    });
    ['dragleave', 'drop'].forEach(function (type) {
      zone.addEventListener(type, function (event) {
        event.preventDefault();
        zone.classList.remove('border-primary', 'bg-primary/10');
      });
    });
    zone.addEventListener('drop', function (event) {
      var files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      var transfer = new DataTransfer();
      transfer.items.add(files[0]);
      input.files = transfer.files;
      render();
    });
    input.addEventListener('change', render);
    render();
  }

  function init() {
    document.querySelectorAll('[data-dropzone]').forEach(setup);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
