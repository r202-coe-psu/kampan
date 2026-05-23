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

print("Updating requisition_timeline_item...");
res = db.requisition_timeline_item.updateMany(
  { organization: { $exists: false } },
  { $set: { organization: orgRef } }
);
print("Requisition Timeline Item matched: " + res.matchedCount + ", modified: " + res.modifiedCount);

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

print("Done.");
