function isSameDay(d1, d2) {
  return (
    d1.getFullYear() === d2.getFullYear() &&
    d1.getMonth() === d2.getMonth() &&
    d1.getDate() === d2.getDate()
  );
}

function isWithinOneDay(d1, d2) {
  return Math.abs(d1.getTime() - d2.getTime()) <= 86400000;
}

function subtractMonths(today, months) {
  const start = new Date(today);
  start.setMonth(start.getMonth() - months);
  if (start.getDate() !== today.getDate()) {
    start.setDate(0);
  }
  return start;
}

const RANGE_CONFIGS = [
  {
    name: "Today",
    compute: (today) => [new Date(today), new Date(today)],
  },
  {
    name: "Yesterday",
    compute: (today) => {
      const d = new Date(today);
      d.setDate(d.getDate() - 1);
      return [d, new Date(d)];
    },
  },
  {
    name: "This Week",
    compute: (today) => {
      const dow = today.getDay();
      const start = new Date(today);
      start.setDate(start.getDate() - (dow === 0 ? 6 : dow - 1));
      return [start, new Date(today)];
    },
  },
  {
    name: "Last 7 Days",
    compute: (today) => {
      const start = new Date(today);
      start.setDate(start.getDate() - 6);
      return [start, new Date(today)];
    },
  },
  {
    name: "This Month",
    compute: (today) => [
      new Date(today.getFullYear(), today.getMonth(), 1),
      new Date(today),
    ],
  },
  {
    name: "Last 30 Days",
    compute: (today) => {
      const start = new Date(today);
      start.setDate(start.getDate() - 29);
      return [start, new Date(today)];
    },
  },
  {
    name: "Last 90 Days",
    compute: (today) => {
      const start = new Date(today);
      start.setDate(start.getDate() - 89);
      return [start, new Date(today)];
    },
  },
  {
    name: "This Year",
    compute: (today) => [new Date(today.getFullYear(), 0, 1), new Date(today)],
  },
  {
    name: "Last 6 Months",
    fuzzyMatch: true,
    compute: (today) => [subtractMonths(today, 6), new Date(today)],
  },
  {
    name: "Last 12 Months",
    fuzzyMatch: true,
    compute: (today) => [subtractMonths(today, 12), new Date(today)],
  },
];

const DATE_FORMAT_OPTIONS = {
  "d/m/Y": { year: "numeric", month: "2-digit", day: "2-digit" },
  "m/d/Y": { year: "numeric", month: "2-digit", day: "2-digit" },
  "Y-m-d": { year: "numeric", month: "2-digit", day: "2-digit" },
  "M j, Y": { year: "numeric", month: "short", day: "numeric" },
};

const DEFAULT_FORMAT_OPTIONS = {
  year: "numeric",
  month: "short",
  day: "numeric",
};

function formatDateForInput(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDisplayDate(dateString) {
  const date = new Date(dateString);
  const scriptTag = document.querySelector("script[data-date-format]");
  const format = scriptTag?.dataset.dateFormat || "Y-m-d";
  const options = DATE_FORMAT_OPTIONS[format] || DEFAULT_FORMAT_OPTIONS;
  return date.toLocaleDateString(undefined, options);
}

function computeDatesForRange(rangeName) {
  if (rangeName === "All Time") {
    return { startDate: "all", endDate: "all" };
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const cfg = RANGE_CONFIGS.find((r) => r.name === rangeName);
  if (!cfg) return null;

  const [start, end] = cfg.compute(today);
  return {
    startDate: formatDateForInput(start),
    endDate: formatDateForInput(end),
  };
}

function detectRangeFromDates(startDateStr, endDateStr) {
  if (startDateStr === "all" && endDateStr === "all") {
    return "All Time";
  }

  const startDate = new Date(startDateStr);
  const endDate = new Date(endDateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (const cfg of RANGE_CONFIGS) {
    const [expStart, expEnd] = cfg.compute(today);
    const startMatch = cfg.fuzzyMatch
      ? isWithinOneDay(startDate, expStart)
      : isSameDay(startDate, expStart);
    if (startMatch && isSameDay(endDate, expEnd)) {
      return cfg.name;
    }
  }

  return `${formatDisplayDate(startDateStr)} - ${formatDisplayDate(endDateStr)}`;
}

const PREDEFINED_RANGES = [
  ...RANGE_CONFIGS.map((r) => ({ name: r.name })),
  { name: "All Time" },
];

function initFromUrlParams(picker) {
  const urlParams = new URLSearchParams(window.location.search);
  const startDateParam = urlParams.get("start-date");
  const endDateParam = urlParams.get("end-date");

  if (startDateParam && endDateParam) {
    picker.startDate = startDateParam;
    picker.endDate = endDateParam;
    picker.selectedRange = detectRangeFromDates(startDateParam, endDateParam);
  }
}

function dateRangePicker() {
  return {
    isOpen: false,
    activeTab: "predefined",
    selectedRange: "Last 12 Months",
    startDate: new Date(new Date().setFullYear(new Date().getFullYear() - 1))
      .toISOString()
      .split("T")[0],
    endDate: new Date().toISOString().split("T")[0],
    customRangeLabel: "",
    predefinedRanges: PREDEFINED_RANGES,

    init() {
      initFromUrlParams(this);
    },

    toggleDropdown() {
      this.isOpen = !this.isOpen;
    },

    selectPredefinedRange(rangeName) {
      const dates = computeDatesForRange(rangeName);
      if (!dates) return;
      this.startDate = dates.startDate;
      this.endDate = dates.endDate;
      this.selectedRange = rangeName;
      this.isOpen = false;
      this.applyDateFilter();
    },

    updateDateRange() {
      if (new Date(this.endDate) < new Date(this.startDate)) {
        this.endDate = this.startDate;
      }
      this.customRangeLabel = `${formatDisplayDate(this.startDate)} - ${formatDisplayDate(this.endDate)}`;
    },

    applyCustomRange() {
      this.selectedRange = this.customRangeLabel;
      this.isOpen = false;
      this.applyDateFilter();
    },

    applyDateFilter() {
      const url = new URL(window.location.href);
      url.searchParams.set("start-date", this.startDate);
      url.searchParams.set("end-date", this.endDate);
      window.location.href = url.toString();
    },
  };
}
