try {
  const savedTheme = localStorage.getItem("vct-scout-theme");
  document.documentElement.dataset.theme = savedTheme === "light" || savedTheme === "dark"
    ? savedTheme
    : (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
} catch (error) {
  console.warn("Could not read the saved theme preference.", error);
  document.documentElement.dataset.theme = matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}
