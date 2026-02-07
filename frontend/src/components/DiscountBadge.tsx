import { Badge } from '@/components/ui/badge';
import { formatCurrency } from '@/utils/cn';

interface DiscountBadgeProps {
  savings: number;
  className?: string;
}

export function DiscountBadge({ savings, className }: DiscountBadgeProps) {
  if (savings <= 0) return null;

  return (
    <Badge variant="savings" className={className}>
      Save {formatCurrency(savings)}
    </Badge>
  );
}
