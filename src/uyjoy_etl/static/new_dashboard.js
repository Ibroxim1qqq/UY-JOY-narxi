(function () {
  const root = document.querySelector("[data-valuation-page]");
  if (!root) {
    return;
  }

  const districts = [
    "Bektemir",
    "Chilonzor",
    "Mirobod",
    "Mirzo Ulugbek",
    "Olmazor",
    "Sergeli",
    "Shayxontohur",
    "Uchtepa",
    "Yakkasaroy",
    "Yangihayot",
    "Yashnobod",
    "Yunusobod",
  ];

  const els = {
    form: document.querySelector("#valuationForm"),
    district: document.querySelector("#valuationDistrict"),
    rooms: document.querySelector("#valuationRooms"),
    area: document.querySelector("#valuationArea"),
    floor: document.querySelector("#valuationFloor"),
    totalFloors: document.querySelector("#valuationTotalFloors"),
    currency: document.querySelector("#valuationCurrency"),
    submit: document.querySelector("#valuationSubmit"),
    error: document.querySelector("#valuationError"),
    result: document.querySelector("#valuationResult"),
    price: document.querySelector("#valuationPrice"),
    unitPrice: document.querySelector("#valuationUnitPrice"),
  };

  init();

  function init() {
    renderDistricts();
    hydrateFromUrl();
    els.form.addEventListener("submit", submitValuation);
    [els.district, els.rooms, els.area, els.floor, els.totalFloors, els.currency].forEach((control) => {
      control.addEventListener("change", syncUrl);
      control.addEventListener("input", syncUrl);
    });
  }

  function renderDistricts() {
    els.district.innerHTML = districts
      .map((district) => `<option value="${escapeAttr(district)}">${escapeHtml(district)}</option>`)
      .join("");
    els.district.value = "Chilonzor";
  }

  function hydrateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    setValue(els.district, params.get("district"));
    setValue(els.rooms, params.get("rooms"));
    setValue(els.area, params.get("area_m2"));
    setValue(els.floor, params.get("floor_number"));
    setValue(els.totalFloors, params.get("total_floors"));
    setValue(els.currency, params.get("currency"));
  }

  function setValue(control, value) {
    if (value == null || value === "") {
      return;
    }
    control.value = value;
  }

  function syncUrl() {
    const params = new URLSearchParams();
    [
      ["district", els.district.value],
      ["rooms", els.rooms.value],
      ["area_m2", els.area.value],
      ["floor_number", els.floor.value],
      ["total_floors", els.totalFloors.value],
      ["currency", els.currency.value],
    ].forEach(([key, value]) => {
      if (value) {
        params.set(key, value);
      }
    });
    const nextUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, "", nextUrl);
  }

  async function submitValuation(event) {
    event.preventDefault();
    hideError();
    hideResult();

    const floor = Number(els.floor.value);
    const totalFloors = Number(els.totalFloors.value);
    if (floor > totalFloors) {
      showError("Qavat jami qavatdan katta bo'lmasligi kerak");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(root.dataset.valuationApiUrl || "/api/apartment-valuation", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          district: els.district.value,
          rooms: els.rooms.value,
          area_m2: els.area.value,
          floor_number: els.floor.value,
          total_floors: els.totalFloors.value,
          currency: els.currency.value || "UZS",
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      renderResult(data);
    } catch (error) {
      showError(error.message || "Bashorat qilishda xatolik yuz berdi");
    } finally {
      setLoading(false);
    }
  }

  function setLoading(isLoading) {
    root.classList.toggle("is-loading", isLoading);
    els.submit.disabled = isLoading;
    els.submit.textContent = isLoading ? "Hisoblanmoqda..." : "Narxni hisoblash";
  }

  function renderResult(data) {
    const prediction = data.prediction || {};
    els.price.textContent = prediction.price_display || "-";
    els.unitPrice.textContent = prediction.unit_price_display || "-";
    els.result.hidden = false;
    els.result.focus({ preventScroll: true });
  }

  function hideResult() {
    els.result.hidden = true;
  }

  function hideError() {
    els.error.hidden = true;
    els.error.textContent = "";
  }

  function showError(message) {
    els.error.textContent = message;
    els.error.hidden = false;
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, "&#96;");
  }
})();
