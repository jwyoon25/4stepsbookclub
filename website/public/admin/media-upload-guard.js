(() => {
  const MAX_MEDIA_FILE_SIZE = 2 * 1024 * 1024;

  function filesFromEvent(event) {
    if (event.type === "drop") {
      return Array.from(event.dataTransfer?.files || []);
    }

    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.type !== "file") {
      return [];
    }

    return Array.from(input.files || []);
  }

  function enforceMediaFileSize(event) {
    const oversizedFile = filesFromEvent(event).find(
      (file) => file.size > MAX_MEDIA_FILE_SIZE
    );

    if (!oversizedFile) {
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();

    if (event.target instanceof HTMLInputElement) {
      event.target.value = "";
    }

    window.alert(
      `파일당 최대 2MB까지 업로드할 수 있습니다.\n${oversizedFile.name}`
    );
  }

  document.addEventListener("change", enforceMediaFileSize, true);
  document.addEventListener("drop", enforceMediaFileSize, true);
})();
