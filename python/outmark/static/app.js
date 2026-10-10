const statusNode = document.querySelector("#status");

fetch("/health")
  .then((response) => {
    if (!response.ok) {
      throw new Error("health request failed");
    }
    return response.json();
  })
  .then((body) => {
    if (body.status !== "ok" || body.data_dir_ready !== true) {
      statusNode.textContent = "The local service responded, but storage is not ready.";
      return;
    }
    if (body.model_present === true) {
      statusNode.textContent = "The local service is running, and a model file is on disk.";
      return;
    }
    statusNode.textContent =
      "The local service is running. Activity generation waits until a model file is installed.";
  })
  .catch(() => {
    statusNode.textContent = "The local service did not respond.";
  });
