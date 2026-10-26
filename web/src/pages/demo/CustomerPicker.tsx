import { CaretDown, Check } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import type { Customer } from "../../api";

interface Props {
  customers: Customer[];
  value: string;
  onChange: (customerId: string) => void;
}

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2);
}

/** "Signed in as" switcher that shows each demo customer's persona. */
export function CustomerPicker({ customers, value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const current = customers.find((c) => c.customer_id === value);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div className="picker" ref={root}>
      <button
        type="button"
        className="picker-button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="avatar" aria-hidden="true">
          {current ? initials(current.name) : ""}
        </span>
        <span className="picker-text">
          <span className="picker-kicker">Signed in as</span>
          <span className="picker-name">{current?.name ?? "Choose a customer"}</span>
        </span>
        <CaretDown weight="bold" aria-hidden="true" />
      </button>
      {open && (
        <ul className="picker-menu" role="listbox" aria-label="Demo customers">
          {customers.map((c) => (
            <li key={c.customer_id} role="option" aria-selected={c.customer_id === value}>
              <button
                type="button"
                className="picker-option"
                onClick={() => {
                  onChange(c.customer_id);
                  setOpen(false);
                }}
              >
                <span className="avatar" aria-hidden="true">
                  {initials(c.name)}
                </span>
                <span className="picker-text">
                  <span className="picker-name">{c.name}</span>
                  <span className="picker-persona">{c.persona}</span>
                </span>
                {c.customer_id === value && <Check weight="bold" aria-hidden="true" className="picker-check" />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
