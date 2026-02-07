import { Badge } from '@/components/ui/badge';
import { cn } from '@/utils/cn';

interface PreferenceOption {
  name: string;
  type: string;
}

interface PreferencesSelectorProps {
  selected: string[];
  onToggle: (preference: string) => void;
  options: readonly PreferenceOption[];
}

export function PreferencesSelector({
  selected,
  onToggle,
  options,
}: PreferencesSelectorProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const isSelected = selected.includes(option.name);
        return (
          <button
            key={option.name}
            type="button"
            onClick={() => onToggle(option.name)}
            className={cn(
              'rounded-full border px-3 py-1.5 text-sm font-medium transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              isSelected
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-input bg-background hover:bg-accent hover:text-accent-foreground'
            )}
          >
            {option.name}
            {option.type === 'allergy' && (
              <span className="ml-1 text-xs opacity-70">(allergy)</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
