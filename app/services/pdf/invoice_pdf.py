"""
Invoice PDF Generation Service
Location: app/services/pdf/invoice_pdf.py

Uses ReportLab for professional PDF generation
"""
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from datetime import datetime
import io
from typing import Optional
from decimal import Decimal


class InvoicePDFGenerator:
    """Generate professional invoice PDFs"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.page_width, self.page_height = A4
        
    def generate_invoice_pdf(
        self,
        invoice,
        business,
        customer,
        logo_path: Optional[str] = None
    ) -> bytes:
        """
        Generate invoice PDF
        
        Returns: PDF as bytes
        """
        buffer = io.BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.5*inch,
            bottomMargin=0.5*inch
        )
        
        # Build PDF content
        elements = []
        
        # Header with logo and business info
        elements.extend(self._build_header(business, logo_path))
        elements.append(Spacer(1, 0.3*inch))
        
        # Invoice title and details
        elements.extend(self._build_invoice_details(invoice))
        elements.append(Spacer(1, 0.3*inch))
        
        # Customer info
        elements.extend(self._build_customer_info(customer, invoice))
        elements.append(Spacer(1, 0.4*inch))
        
        # Line items table
        elements.extend(self._build_items_table(invoice.items))
        elements.append(Spacer(1, 0.3*inch))
        
        # Totals
        elements.extend(self._build_totals(invoice))
        elements.append(Spacer(1, 0.5*inch))
        
        # Payment terms and notes
        if invoice.payment_terms or invoice.notes:
            elements.extend(self._build_terms_and_notes(invoice))
        
        # Footer
        elements.append(Spacer(1, 0.3*inch))
        elements.extend(self._build_footer(business))
        
        # Build PDF
        doc.build(elements)
        
        # Get PDF bytes
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        return pdf_bytes
    
    def _build_header(self, business, logo_path):
        """Build PDF header with logo and business info"""
        elements = []
        
        # Header table
        header_data = []
        
        # Logo column
        if logo_path:
            try:
                logo = Image(logo_path, width=1.5*inch, height=1.5*inch)
                logo_cell = logo
            except:
                logo_cell = ""
        else:
            logo_cell = ""
        
        # Business info column
        business_info = f"""
        <b><font size="14" color="{business.primary_color}">{business.business_name}</font></b><br/>
        {business.address or ''}<br/>
        {business.city or ''}, {business.state or ''}<br/>
        {business.phone or ''}<br/>
        {business.email or ''}<br/>
        {f"TIN: {business.tin}" if business.tin else ''}
        """
        
        header_data = [[logo_cell, Paragraph(business_info, self.styles['Normal'])]]
        
        header_table = Table(header_data, colWidths=[2*inch, 4*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        
        elements.append(header_table)
        
        return elements
    
    def _build_invoice_details(self, invoice):
        """Build invoice number and dates"""
        elements = []
        
        # Invoice title
        title_style = ParagraphStyle(
            'InvoiceTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1E40AF'),
            alignment=TA_CENTER
        )
        elements.append(Paragraph("INVOICE", title_style))
        elements.append(Spacer(1, 0.2*inch))
        
        # Invoice details table
        details_data = [
            ['Invoice Number:', invoice.invoice_number],
            ['Issue Date:', invoice.issue_date.strftime('%d %B %Y')],
            ['Due Date:', invoice.due_date.strftime('%d %B %Y')],
            ['Status:', invoice.status.value]
        ]
        
        details_table = Table(details_data, colWidths=[1.5*inch, 2*inch])
        details_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ]))
        
        elements.append(details_table)
        
        return elements
    
    def _build_customer_info(self, customer, invoice):
        """Build customer information section"""
        elements = []
        
        customer_title = ParagraphStyle(
            'CustomerTitle',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#374151')
        )
        
        elements.append(Paragraph("BILL TO:", customer_title))
        elements.append(Spacer(1, 0.1*inch))
        
        customer_info = f"""
        <b>{customer.name}</b><br/>
        {customer.address or ''}<br/>
        {customer.city or ''}, {customer.state or ''}<br/>
        {customer.phone or ''}<br/>
        {customer.email or ''}<br/>
        {f"TIN: {customer.tin}" if customer.tin else ''}
        """
        
        elements.append(Paragraph(customer_info, self.styles['Normal']))
        
        return elements
    
    def _build_items_table(self, items):
        """Build line items table"""
        elements = []
        
        # Table header
        header = ['Description', 'Qty', 'Unit Price', 'Discount', 'Tax', 'Total']
        
        # Table data
        data = [header]
        
        for item in sorted(items, key=lambda x: x.sort_order):
            data.append([
                item.description,
                f"{float(item.quantity):.2f}",
                f"₦{float(item.unit_price):,.2f}",
                f"₦{float(item.discount_amount):,.2f}",
                f"₦{float(item.tax_amount):,.2f}",
                f"₦{float(item.line_total):,.2f}"
            ])
        
        # Create table
        table = Table(data, colWidths=[3*inch, 0.6*inch, 1*inch, 0.9*inch, 0.8*inch, 1.1*inch])
        
        # Style table
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E40AF')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Body
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            
            # Borders
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('LINEABOVE', (0, 0), (-1, 0), 2, colors.HexColor('#1E40AF')),
            
            # Alternating rows
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F4F6')])
        ]))
        
        elements.append(table)
        
        return elements
    
    def _build_totals(self, invoice):
        """Build totals section"""
        elements = []
        
        # Totals data
        totals_data = [
            ['Subtotal:', f"₦{float(invoice.subtotal):,.2f}"],
            ['Discount:', f"₦{float(invoice.discount_amount):,.2f}"],
            ['Tax (VAT):', f"₦{float(invoice.tax_amount):,.2f}"],
            ['', ''],
            ['TOTAL:', f"₦{float(invoice.total_amount):,.2f}"],
            ['Paid:', f"₦{float(invoice.paid_amount):,.2f}"],
            ['BALANCE DUE:', f"₦{float(invoice.outstanding_amount):,.2f}"]
        ]
        
        # Create table (right-aligned)
        totals_table = Table(totals_data, colWidths=[1.5*inch, 1.5*inch], hAlign='RIGHT')
        
        totals_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, 2), 'Helvetica'),
            ('FONTNAME', (1, 0), (1, 2), 'Helvetica'),
            ('FONTNAME', (0, 4), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 4), (1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('LINEABOVE', (0, 4), (-1, 4), 2, colors.black),
            ('LINEBELOW', (0, -1), (-1, -1), 2, colors.black),
            ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#DC2626')),
        ]))
        
        elements.append(totals_table)
        
        return elements
    
    def _build_terms_and_notes(self, invoice):
        """Build payment terms and notes"""
        elements = []
        
        if invoice.payment_terms:
            terms_style = ParagraphStyle(
                'Terms',
                parent=self.styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#6B7280')
            )
            elements.append(Paragraph(f"<b>Payment Terms:</b> {invoice.payment_terms}", terms_style))
            elements.append(Spacer(1, 0.1*inch))
        
        if invoice.notes:
            notes_style = ParagraphStyle(
                'Notes',
                parent=self.styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#6B7280')
            )
            elements.append(Paragraph(f"<b>Notes:</b> {invoice.notes}", notes_style))
        
        return elements
    
    def _build_footer(self, business):
        """Build footer"""
        elements = []
        
        footer_style = ParagraphStyle(
            'Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#9CA3AF'),
            alignment=TA_CENTER
        )
        
        footer_text = f"""
        Thank you for your business!<br/>
        For questions about this invoice, please contact {business.email or business.phone}
        """
        
        elements.append(Paragraph(footer_text, footer_style))
        
        return elements


# Convenience function
def generate_invoice_pdf(invoice, business, customer, logo_path=None) -> bytes:
    """Generate invoice PDF - convenience function"""
    generator = InvoicePDFGenerator()
    return generator.generate_invoice_pdf(invoice, business, customer, logo_path)