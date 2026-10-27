/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ColumnDef, Row } from "@tanstack/react-table";
import { download, generateCsv, mkConfig } from "export-to-csv";

export const csvConfig = (workspaceSlug: string, suffix?: string) =>
  mkConfig({
    fieldSeparator: ",",
    filename: `${workspaceSlug}-analytics${suffix ? `-${suffix}` : ""}`,
    decimalSeparator: ".",
    useKeysAsHeaders: true,
  });

export const exportCSV = <T>(rows: Row<T>[], columns: ColumnDef<T>[], workspaceSlug: string) => {
  const rowData = rows.map((row) => {
    const exportColumns = columns.map((col) => col.meta?.export);
    const cells = exportColumns.reduce((acc: Record<string, string | number>, col) => {
      if (col) {
        const cell = col?.value(row) ?? "-";
        acc[col.label ?? col.key] = cell;
      }
      return acc;
    }, {});
    return cells;
  });
  const csv = generateCsv(csvConfig(workspaceSlug))(rowData);
  download(csvConfig(workspaceSlug))(csv);
};

export const exportRowsCSV = (
  rows: Record<string, string | number | null | undefined>[],
  workspaceSlug: string,
  suffix: string
) => {
  const config = csvConfig(workspaceSlug, suffix);
  const csv = generateCsv(config)(
    rows.map((row) => Object.fromEntries(Object.entries(row).map(([key, value]) => [key, value ?? ""])))
  );
  download(config)(csv);
};
