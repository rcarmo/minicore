import { inventory } from "./feature-inventory";
const records = await inventory(import.meta.dir + "/../..");
console.log(
  records
    .filter((f) => f.status === "implemented" && f.runner === process.argv[2])
    .map((f) => f.path)
    .join(" "),
);
