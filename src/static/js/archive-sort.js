document.addEventListener("alpine:init", () => {
  Alpine.data("archiveSort", () => ({
    sort: "",
    sortDir: "",
    search: "",
    defaultSortDirs: {
      score: "desc",
      title: "asc",
      start_date: "asc",
      end_date: "desc",
    },
    sortLabels: {},

    init() {
      const el = this.$el;
      this.sort = el.dataset.sort;
      this.sortDir = el.dataset.sortDir;
      this.search = el.dataset.search || "";
      this.sortLabels = JSON.parse(el.dataset.sortLabels);
    },
  }));
});
