document.addEventListener("alpine:init", () => {
  Alpine.data("searchBar", () => ({
    isOpen: false,
    selectedType: { display: "", value: "" },
    mediaTypes: [],
    suggestOpen: false,
    highlightIndex: -1,
    currentQuery: "",
    localTimer: null,
    apiTimer: null,

    init() {
      const el = this.$el;
      this.selectedType = {
        display: el.dataset.selectedDisplay,
        value: el.dataset.selectedValue,
      };
      this.mediaTypes = JSON.parse(el.dataset.mediaTypes);
      this._urlLocal = el.dataset.urlLocal;
      this._urlApi = el.dataset.urlApi;
      this._urlRecent = el.dataset.urlRecent;
    },

    getPlaceholder() {
      return `Search ${this.selectedType.display.toLowerCase()}...`;
    },

    handleInput(e) {
      const q = e.target.value.trim();
      this.currentQuery = q;
      this.highlightIndex = -1;
      clearTimeout(this.localTimer);
      clearTimeout(this.apiTimer);

      if (q.length < 2) {
        this.suggestOpen = false;
        this.$refs.suggestRecent.innerHTML = "";
        this.$refs.suggestLocal.innerHTML = "";
        this.$refs.suggestApi.innerHTML = "";
        return;
      }

      this.suggestOpen = true;
      const localUrl = this._urlLocal + "?q=" + encodeURIComponent(q);
      const apiUrl = this._urlApi + "?q=" + encodeURIComponent(q);
      const savedQuery = q;

      this.localTimer = setTimeout(() => {
        fetch(localUrl, { headers: { "X-Requested-With": "XMLHttpRequest" } })
          .then((r) => r.text())
          .then((html) => {
            if (this.currentQuery === savedQuery)
              this.$refs.suggestLocal.innerHTML = html;
          });
      }, 200);

      if (q.length >= 3) {
        this.$refs.suggestApi.innerHTML =
          this.$refs.suggestLoading.innerHTML;
        this.apiTimer = setTimeout(() => {
          const localItems = this.$refs.suggestLocal.querySelectorAll(
            ".suggest-item[data-media-id]",
          );
          const keys = [...localItems]
            .map((el) => el.dataset.mediaId + ":" + el.dataset.source)
            .join(",");
          const fullApiUrl = keys
            ? apiUrl + "&local_keys=" + encodeURIComponent(keys)
            : apiUrl;
          fetch(fullApiUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
          })
            .then((r) => r.text())
            .then((html) => {
              if (this.currentQuery === savedQuery)
                this.$refs.suggestApi.innerHTML = html;
            });
        }, 500);
      } else {
        this.$refs.suggestApi.innerHTML = "";
      }
    },

    getAllItems() {
      return [
        ...this.$refs.suggestDropdown.querySelectorAll(".suggest-item"),
      ];
    },

    handleKeydown(e) {
      if (!this.suggestOpen) return;
      const items = this.getAllItems();
      if (!items.length) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        this.highlightIndex = (this.highlightIndex + 1) % items.length;
        this.updateHighlight(items);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        this.highlightIndex =
          this.highlightIndex <= 0
            ? items.length - 1
            : this.highlightIndex - 1;
        this.updateHighlight(items);
      } else if (e.key === "Enter" && this.highlightIndex >= 0) {
        e.preventDefault();
        const item = items[this.highlightIndex];
        if (item.tagName === "A") {
          window.location.href = item.href;
        } else if (item.dataset.title) {
          this.$refs.searchInput.value = item.dataset.title;
          this.suggestOpen = false;
          this.$refs.searchForm.submit();
        }
      } else if (e.key === "Escape") {
        this.suggestOpen = false;
      }
    },

    updateHighlight(items) {
      items.forEach((el, i) => {
        const active = i === this.highlightIndex;
        el.classList.toggle("bg-card", active);
        el.classList.toggle("text-white", active);
        if (el.getAttribute("role") === "option")
          el.setAttribute("aria-selected", active);
      });
      if (items[this.highlightIndex])
        items[this.highlightIndex].scrollIntoView({ block: "nearest" });
    },

    handleFocus() {
      if (this.currentQuery.length >= 2) {
        this.suggestOpen = true;
      } else if (this.currentQuery.length === 0) {
        const url =
          this._urlRecent +
          "?type=" +
          encodeURIComponent(this.selectedType.value);
        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
          .then((r) => r.text())
          .then((html) => {
            if (html.trim()) {
              this.$refs.suggestRecent.innerHTML = html;
              this.$refs.suggestLocal.innerHTML = "";
              this.$refs.suggestApi.innerHTML = "";
              this.suggestOpen = true;
            }
          });
      }
    },

    selectItem(e) {
      const item = e.target.closest(".suggest-item");
      if (!item) return;
      if (item.tagName === "A") return;
      if (item.dataset.title) {
        this.$refs.searchInput.value = item.dataset.title;
        this.suggestOpen = false;
        this.$refs.searchForm.submit();
      }
    },
  }));
});
