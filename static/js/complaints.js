/*
  Student complaint pages: progressive enhancement only. Every rule is enforced on the
  server; without JavaScript the pages work with plain forms.
  - Subcategories: show only those of the chosen category (hide the field if it has none).
  - Duplicate notice (DEC-225): if the student already has open complaints in the chosen
    category, say so. It never blocks submission.
  - Forms marked data-once-submit disable their button after the first submit.
*/
(function () {
  "use strict";

  var category = document.querySelector("[data-complaint-category]");
  var subcategory = document.querySelector("[data-complaint-subcategory]");
  var subField = document.querySelector("[data-subcategory-field]");

  if (category && subcategory && subField) {
    // Keep the full grouped list and rebuild the select from it on each change.
    var groups = Array.prototype.map.call(subcategory.querySelectorAll("optgroup"), function (g) {
      return { label: g.label, node: g.cloneNode(true) };
    });
    var emptyOption = subcategory.querySelector('option[value=""]');

    var filterSubcategories = function () {
      var chosen = category.selectedIndex > 0 ? category.options[category.selectedIndex].text : "";
      var previous = subcategory.value;
      var match = groups.filter(function (g) { return g.label === chosen; })[0];
      subcategory.innerHTML = "";
      if (emptyOption) subcategory.appendChild(emptyOption);
      if (match) {
        Array.prototype.forEach.call(match.node.children, function (option) {
          subcategory.appendChild(option.cloneNode(true));
        });
      }
      subcategory.value = Array.prototype.some.call(subcategory.options, function (o) { return o.value === previous; }) ? previous : "";
      subField.hidden = !match;
    };
    category.addEventListener("change", filterSubcategories);
    filterSubcategories();
  }

  var notice = document.querySelector("[data-duplicate-notice]");
  var data = document.getElementById("open-complaints");
  if (category && notice && data) {
    var openByCategory = JSON.parse(data.textContent);
    var list = notice.querySelector("[data-duplicate-list]");
    var showNotice = function () {
      var items = openByCategory[category.value] || [];
      list.innerHTML = "";
      items.forEach(function (item) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = item.url;
        var ref = document.createElement("span");
        ref.className = "sa-ref";
        ref.textContent = item.reference;
        a.appendChild(ref);
        a.appendChild(document.createTextNode(" " + item.title));
        li.appendChild(a);
        list.appendChild(li);
      });
      notice.hidden = items.length === 0;
    };
    category.addEventListener("change", showNotice);
    showNotice();
  }

  Array.prototype.forEach.call(document.querySelectorAll("form[data-once-submit]"), function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector('button[type="submit"]');
      if (!button) return;
      // Disable after the browser has taken the submission, so the form still posts.
      window.setTimeout(function () {
        button.disabled = true;
        if (button.dataset.submitLabel) button.textContent = button.dataset.submitLabel;
      }, 0);
    });
  });
})();

/*
  Batch Advisor workspace (Complaints Part 3), progressive enhancement only:
  - the status note's label follows the chosen status (required for Resolved and Rejected;
    the form and the service enforce it either way);
  - after a validation error, focus moves to the error summary of the open panel.
*/
(function () {
  "use strict";

  var statusForm = document.querySelector("form[data-status-form]");
  var labelsData = document.getElementById("status-note-labels");
  if (statusForm && labelsData) {
    var labels = JSON.parse(labelsData.textContent);
    var note = statusForm.querySelector("textarea[name='note']");
    var noteLabel = note ? statusForm.querySelector("label[for='" + note.id + "']") : null;
    var update = function () {
      var chosen = statusForm.querySelector("input[name='new_status']:checked");
      var info = chosen ? labels[chosen.value] : null;
      if (!noteLabel || !info) return;
      noteLabel.textContent = info.label + (info.required ? " (required)" : " (optional)");
      note.required = info.required;
    };
    statusForm.addEventListener("change", update);
    update();
  }

  var errorSummary = document.querySelector("[data-error-focus]");
  if (errorSummary) {
    errorSummary.scrollIntoView({ block: "center" });
    errorSummary.focus({ preventScroll: true });
  }
})();
