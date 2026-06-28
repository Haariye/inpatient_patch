frappe.query_reports["Operative Workflow Status"] = {
    filters: [
        { fieldname: "inpatient_record", label: "Inpatient Record", fieldtype: "Link",
          options: "Inpatient Record" },
    ],
    formatter(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname === "stage" && data) {
            const colors = { "Pre-Operative": "#f59e0b", "Intra-Operative": "#ef4444",
                             "Post-Operative": "#3b82f6", "Discharged": "#10b981" };
            const c = colors[data.stage] || "#6b7280";
            value = `<span style="color:#fff;background:${c};padding:2px 8px;border-radius:10px;">${data.stage}</span>`;
        }
        return value;
    },
};
