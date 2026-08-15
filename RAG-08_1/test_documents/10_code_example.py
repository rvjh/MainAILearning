"""
Example Python Code for RAG System
This file demonstrates code chunking strategies.
"""

def calculate_revenue(quarter, base_revenue):
    """
    Calculate revenue for a given quarter.
    
    Args:
        quarter: Quarter number (1-4)
        base_revenue: Base revenue amount
    
    Returns:
        Calculated revenue with growth factor
    """
    growth_factor = 1.0 + (quarter * 0.05)  # 5% growth per quarter
    return base_revenue * growth_factor


class FinancialReport:
    """Class for generating financial reports."""
    
    def __init__(self, company_name, year):
        self.company_name = company_name
        self.year = year
        self.revenue_data = []
    
    def add_quarter(self, quarter, revenue):
        """Add quarterly revenue data."""
        self.revenue_data.append({
            'quarter': quarter,
            'revenue': revenue
        })
    
    def get_total_revenue(self):
        """Calculate total revenue for the year."""
        return sum(q['revenue'] for q in self.revenue_data)
    
    def generate_report(self):
        """Generate formatted financial report."""
        report = f"Financial Report for {self.company_name} - {self.year}\n"
        report += "=" * 50 + "\n"
        for q in self.revenue_data:
            report += f"Q{q['quarter']}: ${q['revenue']:,.2f}\n"
        report += f"\nTotal: ${self.get_total_revenue():,.2f}\n"
        return report


if __name__ == "__main__":
    report = FinancialReport("QuantumFlux Industries", 2024)
    report.add_quarter(1, 2100000)
    report.add_quarter(2, 2800000)
    report.add_quarter(3, 3400000)
    report.add_quarter(4, 4200000)
    print(report.generate_report())
