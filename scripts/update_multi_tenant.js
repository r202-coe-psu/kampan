db = db.getSiblingDB('kampandb');

var orgId = ObjectId("6661c367df36be9c312058ae");
var orgRef = DBRef("organizations", orgId);

print("Updating procurements...");
var res = db.procurements.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Procurements matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

print("Updating requisitions...");
res = db.requisitions.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Requisitions matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

print("Updating requisition_timeline...");
res = db.requisition_timeline.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Requisition Timeline matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

print("Updating requisition_timeline_items...");
res = db.requisition_timeline_items.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Requisition Timeline Items matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

print("Updating mas...");
res = db.mas.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("MAS matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

print("Updating reservations...");
res = db.reservations.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Reservations matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

print("Updating documents...");
res = db.documents.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Documents matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

print("Updating suppliers...");
res = db.suppliers.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Suppliers matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

print("Updating requisition_timeline_logs...");
res = db.requisition_timeline_logs.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Requisition Timeline Logs matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

const remainingCollections = [
  "categories",
  "divisions",
  "email_templates",
  "inventories",
  "inventory_engagement_file",
  "checkout_items",
  "order_items",
  "registration_items",
  "items",
  "item_positions",
  "item_snapshots",
  "lost_break_items",
  "organization_user_roles",
  "logos",
  "car_applications",
  "motorcycle_applications",
  "cars",
  "motorcycles",
  "car_feedbacks",
  "warehouses",
  "approved_checkout_items"
];

for (let i = 0; i < remainingCollections.length; i++) {
  let collName = remainingCollections[i];
  print("Updating " + collName + "...");
  let resColl = db[collName].updateMany(
    { organization: { $exists: false } },
    { $set: { organization: orgRef } }
  );
  print(collName + " matched: " + resColl.matchedCount + ", modified: " + resColl.modifiedCount);
}

print("Done.");
