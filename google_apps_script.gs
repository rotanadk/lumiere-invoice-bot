const SPREADSHEET_ID = "1eIGudtbR_tZ8m1Y-gZO6INWnbjyA4tax9wqfoH6WYL0";

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet() {
  return jsonResponse({ok: true, service: "Lumiere Order Transactions"});
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);

    const expectedSecret = PropertiesService.getScriptProperties().getProperty("WEBHOOK_SECRET");
    if (!expectedSecret) {
      return jsonResponse({ok: false, error: "WEBHOOK_SECRET is not configured in Apps Script."});
    }

    const body = JSON.parse((e.postData && e.postData.contents) || "{}");
    if (body.secret !== expectedSecret) {
      return jsonResponse({ok: false, error: "Unauthorized"});
    }

    const order = body.order;
    if (!order || !order.telegram_message_id || !Array.isArray(order.items)) {
      return jsonResponse({ok: false, error: "Invalid order payload"});
    }

    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    const itemsSheet = ss.getSheetByName("Order_Items");
    const ordersSheet = ss.getSheetByName("Orders");

    if (!itemsSheet || !ordersSheet) {
      return jsonResponse({ok: false, error: "Order_Items or Orders tab is missing."});
    }

    const msgId = String(order.telegram_message_id);

    // Upsert behavior: if Railway retries the same message, replace old rows instead of duplicating them.
    deleteRowsByMessageId(itemsSheet, 12, msgId); // Order_Items column L
    deleteRowsByMessageId(ordersSheet, 10, msgId); // Orders column J

    order.items.forEach(function(item) {
      itemsSheet.appendRow([
        order.date || "",
        order.time || "",
        order.order_no || "",
        order.customer || "",
        item.product || "",
        item.qty || item.qty_display || "",
        item.unit || "kg",
        Number(item.unit_price || 0),
        Number(item.amount || 0),
        order.payment_status || "Unpaid",
        order.staff || "",
        msgId,
        order.raw_order || ""
      ]);
    });

    ordersSheet.appendRow([
      order.date || "",
      order.time || "",
      order.order_no || "",
      order.customer || "",
      order.items.length,
      Number(order.total_qty_kg || 0),
      Number(order.order_total || 0),
      order.payment_status || "Unpaid",
      order.staff || "",
      msgId,
      order.raw_order || ""
    ]);

    SpreadsheetApp.flush();

    return jsonResponse({
      ok: true,
      message_id: msgId,
      item_rows: order.items.length,
      order_total: Number(order.order_total || 0)
    });
  } catch (err) {
    return jsonResponse({ok: false, error: String(err && err.message ? err.message : err)});
  } finally {
    try { lock.releaseLock(); } catch (e) {}
  }
}

function deleteRowsByMessageId(sheet, messageIdColumn, messageId) {
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  const values = sheet.getRange(2, messageIdColumn, lastRow - 1, 1).getDisplayValues();
  for (let i = values.length - 1; i >= 0; i--) {
    if (String(values[i][0]) === String(messageId)) {
      sheet.deleteRow(i + 2);
    }
  }
}
