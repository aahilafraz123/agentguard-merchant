import {
  CellStyleModule,
  ClientSideRowModelModule,
  ModuleRegistry,
  NumberFilterModule,
  PaginationModule,
  QuickFilterModule,
  RenderApiModule,
  TextFilterModule,
  TooltipModule,
  ValidationModule,
  themeQuartz,
  type ColDef,
  type GetRowIdParams,
  type RowClickedEvent,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useEffect, useRef } from "react";

// Only the features the console uses, to keep the bundle small.
ModuleRegistry.registerModules([
  ClientSideRowModelModule,
  CellStyleModule,
  TextFilterModule,
  NumberFilterModule,
  QuickFilterModule,
  PaginationModule,
  RenderApiModule,
  TooltipModule,
  ...(import.meta.env.DEV ? [ValidationModule] : []),
]);

// The grid reads the app's CSS tokens, so it follows light and dark mode with the rest of the UI.
const theme = themeQuartz.withParams({
  fontFamily: "var(--font-sans)",
  fontSize: 13,
  headerFontSize: 12,
  headerFontWeight: 500,
  backgroundColor: "var(--surface)",
  foregroundColor: "var(--text)",
  textColor: "var(--text)",
  subtleTextColor: "var(--text-3)",
  headerTextColor: "var(--text-2)",
  headerBackgroundColor: "var(--surface-2)",
  borderColor: "var(--border)",
  rowBorder: { color: "var(--border)" },
  wrapperBorder: { color: "var(--border)" },
  wrapperBorderRadius: 8,
  borderRadius: 6,
  accentColor: "var(--accent)",
  rowHoverColor: "var(--hover)",
  selectedRowBackgroundColor: "var(--accent-soft)",
  oddRowBackgroundColor: "var(--surface)",
  chromeBackgroundColor: "var(--surface-2)",
  inputBackgroundColor: "var(--surface)",
  inputBorder: { color: "var(--border-strong)" },
  menuBackgroundColor: "var(--surface)",
  menuBorder: { color: "var(--border)" },
  spacing: 7,
  rowVerticalPaddingScale: 1.25,
  cellHorizontalPaddingScale: 0.9,
  iconSize: 14,
});

const defaultColDef: ColDef = {
  sortable: true,
  resizable: true,
  filter: true,
  suppressHeaderMenuButton: false,
  minWidth: 90,
};

interface Props<T> {
  rows: T[] | undefined;
  columns: ColDef<T>[];
  rowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  quickFilter?: string;
  pageSize?: number;
  emptyMessage?: string;
}

export function Grid<T>({ rows, columns, rowId, onRowClick, quickFilter, pageSize = 20, emptyMessage }: Props<T>) {
  const paginate = (rows?.length ?? 0) > pageSize;
  const grid = useRef<AgGridReact<T>>(null);
  // Columns are rebuilt when lookups (like customer names) arrive; redraw cells that already rendered.
  useEffect(() => {
    grid.current?.api?.refreshCells({ force: true });
  }, [columns]);
  return (
    <div className={`grid ${onRowClick ? "is-clickable" : ""}`}>
      <AgGridReact<T>
        ref={grid}
        theme={theme}
        rowData={rows ?? null}
        columnDefs={columns}
        defaultColDef={defaultColDef}
        getRowId={(p: GetRowIdParams<T>) => rowId(p.data)}
        onRowClicked={onRowClick ? (e: RowClickedEvent<T>) => e.data && onRowClick(e.data) : undefined}
        quickFilterText={quickFilter}
        domLayout="autoHeight"
        pagination={paginate}
        paginationPageSize={pageSize}
        paginationPageSizeSelector={false}
        animateRows
        suppressCellFocus
        overlayNoRowsTemplate={`<span class="grid-empty">${emptyMessage ?? "Nothing here yet"}</span>`}
      />
    </div>
  );
}
