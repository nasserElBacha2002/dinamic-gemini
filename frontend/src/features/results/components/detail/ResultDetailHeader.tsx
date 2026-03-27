/**
 * Sprint 4.3 — Result detail context: `PageHeader` with breadcrumbs (inventory → source list → result).
 */

import type { ReactNode } from 'react';
import { PageHeader, type PageHeaderBreadcrumb } from '../../../../components/shell';

export interface ResultDetailHeaderProps {
  breadcrumbs: PageHeaderBreadcrumb[];
  title: string;
  subtitle?: ReactNode;
}

export default function ResultDetailHeader({ breadcrumbs, title, subtitle }: ResultDetailHeaderProps) {
  return <PageHeader breadcrumbs={breadcrumbs} title={title} subtitle={subtitle} />;
}
