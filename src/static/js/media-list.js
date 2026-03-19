document.addEventListener("alpine:init", () => {
  Alpine.data("mediaList", () => ({
    sort: "",
    sortDir: "",
    status: "",
    layout: "",
    search: "",
    selecting: false,
    selected: [],
    lastSelected: null,
    defaultSortDirs: {
      score: "desc",
      title: "asc",
      progress: "desc",
      status: "asc",
      start_date: "asc",
      end_date: "desc",
    },
    statusLabels: {},
    sortLabels: {},
    activeTab: "collection",

    init() {
      const el = this.$el;
      this.sort = el.dataset.sort;
      this.sortDir = el.dataset.sortDir;
      this.status = el.dataset.status;
      this.layout = el.dataset.layout;
      this.search = el.dataset.search || "";
      this.activeTab = el.dataset.activeTab || "collection";
      this.statusLabels = JSON.parse(el.dataset.statusLabels);
      this.sortLabels = JSON.parse(el.dataset.sortLabels);
    },

    toggleItem(id, event) {
      if (event && event.shiftKey && this.lastSelected) {
        const all = [...document.querySelectorAll("[data-bulk-id]")].map(
          (el) => el.dataset.bulkId,
        );
        const from = all.indexOf(this.lastSelected);
        const to = all.indexOf(id);
        if (from !== -1 && to !== -1) {
          const range = all.slice(
            Math.min(from, to),
            Math.max(from, to) + 1,
          );
          range.forEach((rid) => {
            if (!this.selected.includes(rid)) this.selected.push(rid);
          });
          this.selected = [...this.selected];
          this.lastSelected = id;
          return;
        }
      }
      this.selected = this.selected.includes(id)
        ? this.selected.filter((sid) => sid !== id)
        : [...this.selected, id];
      this.lastSelected = id;
    },
  }));
});
