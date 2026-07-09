frappe.query_reports["Inpatient Census"] = {
    filters: [
        { fieldname: "department", label: "Medical Department", fieldtype: "Link",
          options: "Medical Department" },
    ],
};
