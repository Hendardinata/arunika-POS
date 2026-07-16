const { PrismaClient } = require('@prisma/client');
const bcrypt = require('bcryptjs');
const { Pool } = require('pg');
const { PrismaPg } = require('@prisma/adapter-pg');
require('dotenv').config();

const connectionString = process.env.DATABASE_URL;
const pool = new Pool({ connectionString });
const adapter = new PrismaPg(pool);
const prisma = new PrismaClient({ adapter });

async function main() {
  try {
    const salt = await bcrypt.genSalt(10);
    const hashedPassword = await bcrypt.hash('admin123', salt);

    const user = await prisma.user.upsert({
      where: { username: 'superadmin' },
      update: { password: hashedPassword, role: 'OWNER' },
      create: {
        username: 'superadmin',
        password: hashedPassword,
        role: 'OWNER',
      },
    });

    console.log('✅ Superadmin created successfully!');
    console.log('Username: superadmin');
    console.log('Password: admin123');
    console.log('Role:', user.role);
  } catch (error) {
    console.error('❌ Failed to create superadmin:', error);
  } finally {
    await prisma.$disconnect();
    await pool.end();
  }
}

main();
