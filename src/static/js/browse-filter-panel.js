document.addEventListener("alpine:init", () => {
  Alpine.data("browseFilterPanel", () => ({
    filtersOpen: false,
    orderValue: "desc",
    chipExpanded: {},
    chipSearch: {},
    multiSelectValues: {},
    chipVisibleLimit: 12,

    init() {
      const el = this.$el;
      this.filtersOpen = el.dataset.hasActiveFilters === "true";
      this.orderValue = el.dataset.order || "desc";
      this.chipExpanded = JSON.parse(el.dataset.chipExpanded || "{}");
      this.multiSelectValues = JSON.parse(el.dataset.multiSelectValues || "{}");
    },

    toggleChip(key, value) {
      const arr = this.multiSelectValues[key] || [];
      const idx = arr.indexOf(value);
      if (idx === -1) {
        arr.push(value);
      } else {
        arr.splice(idx, 1);
      }
      this.multiSelectValues[key] = [...arr];
      this.$nextTick(() =>
        document.getElementById("browse-filter-form").requestSubmit(),
      );
    },

    hasChip(key, value) {
      return (this.multiSelectValues[key] || []).includes(value);
    },

    getMultiSelectValue(key) {
      return (this.multiSelectValues[key] || []).join(",");
    },

    chipVisible(key, label, index, value) {
      if (this.hasChip(key, value)) return true;
      const search = (this.chipSearch[key] || "").toLowerCase();
      if (search && !label.toLowerCase().includes(search)) return false;
      if (!this.chipExpanded[key] && !search && index >= this.chipVisibleLimit)
        return false;
      return true;
    },
  }));
});
