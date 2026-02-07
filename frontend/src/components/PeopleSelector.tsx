import { Minus, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface PeopleSelectorProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
}

export function PeopleSelector({
  value,
  onChange,
  min = 1,
  max = 20,
}: PeopleSelectorProps) {
  const decrement = () => {
    if (value > min) {
      onChange(value - 1);
    }
  };

  const increment = () => {
    if (value < max) {
      onChange(value + 1);
    }
  };

  return (
    <div className="flex items-center gap-4">
      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={decrement}
        disabled={value <= min}
        aria-label="Decrease people count"
      >
        <Minus className="h-4 w-4" />
      </Button>

      <div className="flex min-w-[80px] flex-col items-center">
        <span className="text-3xl font-bold">{value}</span>
        <span className="text-sm text-muted-foreground">
          {value === 1 ? 'person' : 'people'}
        </span>
      </div>

      <Button
        type="button"
        variant="outline"
        size="icon"
        onClick={increment}
        disabled={value >= max}
        aria-label="Increase people count"
      >
        <Plus className="h-4 w-4" />
      </Button>
    </div>
  );
}
