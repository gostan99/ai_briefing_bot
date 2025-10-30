import { useMemo } from "react";
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import dayjs from "dayjs";
import { VideoStatus } from "../types";
import { DeleteButton } from "./DeleteButton";

interface VideoTableProps {
  videos: VideoStatus[];
  onSelect: (video: VideoStatus) => void;
  onDelete: (videoId: string) => Promise<void>;
}

export function VideoTable({ videos, onSelect, onDelete }: VideoTableProps) {
  const columns = useMemo<ColumnDef<VideoStatus>[]>(
    () => [
      {
        header: "Video",
        accessorKey: "title",
        cell: (info) => (
          <div>
            <strong>{info.row.original.title}</strong>
            <div className="subtitle">{info.row.original.channel ?? "Unknown"}</div>
          </div>
        ),
      },
      {
        header: "Transcript",
        accessorKey: "transcript_status",
        cell: (info) => <StatusBadge value={info.getValue() as string} />,
      },
      {
        header: "Metadata",
        accessorFn: (row) => row.metadata.status,
        cell: (info) => <StatusBadge value={info.getValue() as string} />,
      },
      {
        header: "Summary",
        accessorFn: (row) => row.summary.status,
        cell: (info) => <StatusBadge value={info.getValue() as string} />,
      },
      {
        header: "Created",
        accessorKey: "created_at",
        cell: (info) => dayjs(info.getValue() as string).format("YYYY-MM-DD HH:mm"),
      },
      {
        header: "",
        accessorKey: "video_id",
        cell: (info) => (
          <DeleteButton videoId={info.getValue() as string} onDelete={onDelete} />
        ),
      },
    ],
    []
  );

  const table = useReactTable({
    data: videos,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id}>
                  {header.isPlaceholder
                    ? null
                    : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} onClick={() => onSelect(row.original)}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ value }: { value: string }) {
  const status = value.toLowerCase();
  const className = `badge badge-${status}`;
  return <span className={className}>{value}</span>;
}
