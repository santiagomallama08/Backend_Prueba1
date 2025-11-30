from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from datetime import datetime
from pathlib import Path
import os

from config.db_config import get_connection

# 📌 Importar carpeta persistente desde main.py
from api.main import REPORTES_DIR   # /data/static/reportes


def generar_reporte_estudio(session_id: str, user_id: int) -> str:
    """
    Genera un reporte PDF completo del estudio DICOM con todas las segmentaciones y modelos STL.
    """

    # 📌 Ruta persistente en el volumen
    reportes_dir = REPORTES_DIR
    reportes_dir.mkdir(parents=True, exist_ok=True)

    # Nombre del archivo PDF
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"reporte_{session_id}_{timestamp}.pdf"
    pdf_path = reportes_dir / pdf_filename

    # Crear documento PDF
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=50,
        bottomMargin=50,
    )

    # Contenedor de elementos
    elements = []

    # Estilos
    styles = getSampleStyleSheet()

    # Estilo personalizado para título
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#4f46e5"),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    # Estilo para subtítulos
    subtitle_style = ParagraphStyle(
        "CustomSubtitle",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=colors.HexColor("#6366f1"),
        spaceAfter=12,
        spaceBefore=12,
        fontName="Helvetica-Bold",
    )

    # Estilo para texto normal
    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=8
    )

    # ============ HEADER ============
    elements.append(Paragraph("REPORTE MÉDICO - ANÁLISIS DICOM", title_style))
    elements.append(Paragraph("Sistema de Prótesis Craneales", styles["Heading3"]))
    elements.append(Spacer(1, 0.3 * inch))

    fecha_reporte = datetime.now().strftime("%d/%m/%Y %H:%M")
    elements.append(Paragraph(f"<b>Fecha de generación:</b> {fecha_reporte}", normal_style))
    elements.append(Spacer(1, 0.2 * inch))

    # ============ CONSULTA A LA BASE DE DATOS ============
    conn = get_connection()
    cur = conn.cursor()

    try:
        # Buscar datos del paciente
        cur.execute(
            """
            SELECT p.nombre_completo, p.tipo_documento, p.documento, p.edad,
                   p.sexo, p.telefono, p.ciudad,
                   ep.fecha_estudio, ep.tipo_estudio, ep.diagnostico
            FROM estudios_paciente ep
            JOIN pacientes p ON ep.paciente_id = p.id
            WHERE ep.session_id = %s AND p.user_id = %s
            LIMIT 1
            """,
            (session_id, user_id),
        )
        paciente_data = cur.fetchone()

        # ================= PACIENTE =================
        if paciente_data:
            elements.append(Paragraph("DATOS DEL PACIENTE", subtitle_style))
            paciente_info = [
                ["Nombre:", paciente_data[0] or "N/A"],
                ["Documento:", f"{paciente_data[1]} {paciente_data[2]}" if paciente_data[1] else "N/A"],
                ["Edad:", f"{paciente_data[3]} años" if paciente_data[3] else "N/A"],
                ["Sexo:", paciente_data[4] or "N/A"],
                ["Teléfono:", paciente_data[5] or "N/A"],
                ["Ciudad:", paciente_data[6] or "N/A"],
            ]

            paciente_table = Table(paciente_info, colWidths=[2 * inch, 4 * inch])
            paciente_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                    ]
                )
            )
            elements.append(paciente_table)
            elements.append(Spacer(1, 0.3 * inch))

            # Información del estudio
            if paciente_data[7] or paciente_data[8]:
                elements.append(Paragraph("INFORMACIÓN DEL ESTUDIO", subtitle_style))
                estudio_info = []
                if paciente_data[7]:
                    estudio_info.append(["Fecha del estudio:", paciente_data[7].strftime("%d/%m/%Y")])
                if paciente_data[8]:
                    estudio_info.append(["Tipo de estudio:", paciente_data[8]])
                if paciente_data[9]:
                    estudio_info.append(["Diagnóstico:", paciente_data[9]])

                estudio_table = Table(estudio_info, colWidths=[2 * inch, 4 * inch])
                estudio_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                            ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                        ]
                    )
                )
                elements.append(estudio_table)
                elements.append(Spacer(1, 0.3 * inch))

        # ================= SEGMENTACIONES 2D =================
        cur.execute(
            """
            SELECT pd.altura, pd.longitud, pd.ancho, pd.volumen, pd.unidad, pd.tipoprotesis, ad.fechacarga
            FROM protesisdimension pd
            LEFT JOIN archivodicom ad ON pd.archivodicomid = ad.archivodicomid
            WHERE ad.rutaarchivo LIKE %s AND pd.user_id = %s
            ORDER BY ad.fechacarga DESC
            """,
            (f"%{session_id}%", user_id),
        )
        seg2d_rows = cur.fetchall()

        if seg2d_rows:
            elements.append(Paragraph("SEGMENTACIONES 2D", subtitle_style))

            for idx, row in enumerate(seg2d_rows, 1):
                elements.append(Paragraph(f"<b>Segmentación 2D #{idx}</b>", normal_style))

                seg2d_data = [
                    ["Altura:", f"{row[0]:.2f} mm" if row[0] else "N/A"],
                    ["Longitud:", f"{row[1]:.2f} mm" if row[1] else "N/A"],
                    ["Ancho:", f"{row[2]:.2f} mm" if row[2] else "N/A"],
                    ["Volumen:", f"{row[3]:.2f} {row[4] or 'mm³'}" if row[3] else "N/A"],
                    ["Tipo:", row[5] or "Cráneo"],
                    ["Fecha:", row[6].strftime("%d/%m/%Y") if row[6] else "N/A"],
                ]

                table = Table(seg2d_data, colWidths=[1.7 * inch, 4.3 * inch])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#ede9fe")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ]
                    )
                )
                elements.append(table)
                elements.append(Spacer(1, 0.2 * inch))

        # ================= SEGMENTACIONES 3D =================
        cur.execute(
            """
            SELECT volume_mm3, surface_mm2, bbox_x_mm, bbox_y_mm, bbox_z_mm, n_slices, created_at
            FROM segmentacion3d
            WHERE session_id = %s AND user_id = %s
            ORDER BY created_at DESC
            """,
            (session_id, user_id),
        )
        seg3d_rows = cur.fetchall()

        if seg3d_rows:
            elements.append(PageBreak())
            elements.append(Paragraph("SEGMENTACIONES 3D", subtitle_style))

            for idx, row in enumerate(seg3d_rows, 1):
                seg3d_data = [
                    ["Volumen:", f"{round(row[0])} mm³"],
                    ["Superficie:", f"{round(row[1])} mm²" if row[1] else "N/A"],
                    ["Dimensiones (BBox):", f"{row[2]:.1f} × {row[3]:.1f} × {row[4]:.1f} mm"],
                    ["Slices:", str(row[5])],
                    ["Fecha:", row[6].strftime("%d/%m/%Y %H:%M") if row[6] else "N/A"],
                ]

                table = Table(seg3d_data, colWidths=[2 * inch, 4 * inch])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#dbeafe")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ]
                    )
                )
                elements.append(Spacer(1, 0.2 * inch))
                elements.append(table)

        # ================= MODELOS STL =================
        cur.execute(
            """
            SELECT path_stl, file_size_bytes, num_vertices, num_caras, created_at
            FROM modelo3d
            WHERE session_id = %s AND user_id = %s
            ORDER BY created_at DESC
            """,
            (session_id, user_id),
        )
        stl_rows = cur.fetchall()

        if stl_rows:
            elements.append(Paragraph("MODELOS STL GENERADOS", subtitle_style))

            for row in stl_rows:
                stl_data = [
                    ["Archivo:", row[0]],
                    ["Tamaño:", f"{row[1] / 1024:.2f} KB" if row[1] else "N/A"],
                    ["Vértices:", str(row[2]) if row[2] else "N/A"],
                    ["Caras:", str(row[3]) if row[3] else "N/A"],
                    ["Fecha:", row[4].strftime("%d/%m/%Y %H:%M") if row[4] else "N/A"],
                ]

                table = Table(stl_data, colWidths=[1.6 * inch, 4.4 * inch])
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#dcfce7")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ]
                    )
                )
                elements.append(Spacer(1, 0.15 * inch))
                elements.append(table)

        # ================= INFORMACIÓN TÉCNICA =================
        elements.append(PageBreak())
        elements.append(Paragraph("INFORMACIÓN TÉCNICA", subtitle_style))

        tech_info = [
            ["Session ID:", session_id],
            ["Sistema:", "DICOM Studio - Análisis de Prótesis Craneales"],
            ["Versión:", "v1.1"],
        ]

        tech_table = Table(tech_info, colWidths=[2 * inch, 4 * inch])
        tech_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f4f6")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(tech_table)

        # ================= FOOTER =================
        elements.append(Spacer(1, 0.5 * inch))
        footer_text = """
            <para align=center fontSize=8 textColor=#666666>
            Este reporte ha sido generado automáticamente por el sistema DICOM Studio.<br/>
            Para uso estrictamente académico y de investigación.<br/>
            © 2025 - Sistema de Análisis DICOM para Prótesis Craneales
            </para>
        """
        elements.append(Paragraph(footer_text, styles["Normal"]))

    finally:
        cur.close()
        conn.close()

    # 📌 Generar PDF
    doc.build(elements)

    # 📌 Devolver ruta pública accesible desde Vercel
    return f"/static/reportes/{pdf_filename}"
