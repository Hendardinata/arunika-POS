import { Router } from 'express';
import { prisma } from '../db';
import multer from 'multer';
import path from 'path';
import fs from 'fs';

const router = Router();

// Setup Multer for Image Upload
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const dir = path.join(__dirname, '../../public/uploads');
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    cb(null, dir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1e9);
    cb(null, 'inventory-' + uniqueSuffix + path.extname(file.originalname));
  },
});
const upload = multer({ storage });

// GET all inventory items
router.get('/', async (req, res) => {
  try {
    const items = await prisma.inventoryItem.findMany();
    res.json(items);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch inventory' });
  }
});

// POST new inventory item
router.post('/', upload.single('image'), async (req, res) => {
  try {
    const { name, stock, unit } = req.body;
    let imageUrl = null;
    if (req.file) {
      imageUrl = `/uploads/${req.file.filename}`;
    }

    const item = await prisma.inventoryItem.create({
      data: { 
        name, 
        stock: parseInt(stock) || 0, 
        unit: unit || 'pcs',
        imageUrl
      },
    });
    // Create initial log
    if (item.stock > 0) {
      await prisma.inventoryLog.create({
        data: { itemId: item.id, quantity: item.stock, type: 'IN', notes: 'Initial stock' }
      });
    }
    res.status(201).json(item);
  } catch (error) {
    res.status(500).json({ error: 'Failed to create inventory item' });
  }
});

// PUT edit inventory item (name, unit, image)
router.put('/:id', upload.single('image'), async (req, res) => {
  try {
    const { id } = req.params;
    const { name, unit } = req.body;

    const existing = await prisma.inventoryItem.findUnique({ where: { id: parseInt(id) } });
    if (!existing) return res.status(404).json({ error: 'Item not found' });

    let imageUrl = existing.imageUrl;
    if (req.file) {
      imageUrl = `/uploads/${req.file.filename}`;
      // Optional: Delete old image here if exists
    }

    const item = await prisma.inventoryItem.update({
      where: { id: parseInt(id) },
      data: { name, unit, imageUrl },
    });
    res.json(item);
  } catch (error) {
    res.status(500).json({ error: 'Failed to update inventory item' });
  }
});

// PUT update stock (adjust in/out)
router.put('/:id/adjust', async (req, res) => {
  try {
    const { id } = req.params;
    const { quantity, type, notes } = req.body; // type: "IN" or "OUT", quantity is absolute positive

    const item = await prisma.inventoryItem.findUnique({ where: { id: parseInt(id) } });
    if (!item) return res.status(404).json({ error: 'Item not found' });

    const q = parseInt(quantity);
    if (isNaN(q) || q <= 0) return res.status(400).json({ error: 'Invalid quantity' });

    const newStock = type === 'IN' ? item.stock + q : item.stock - q;
    
    const updated = await prisma.inventoryItem.update({
      where: { id: parseInt(id) },
      data: { stock: newStock }
    });

    await prisma.inventoryLog.create({
      data: { itemId: parseInt(id), quantity: q, type, notes }
    });

    res.json(updated);
  } catch (error) {
    res.status(500).json({ error: 'Failed to adjust inventory stock' });
  }
});

// GET /opname/today
router.get('/opname/today', async (req, res) => {
  try {
    const opname = await prisma.dailyOpname.findFirst({
      where: { status: 'OPEN' },
      include: { items: { include: { inventoryItem: true } } },
      orderBy: { createdAt: 'desc' }
    });
    
    if (opname) {
      // Dynamically compute addedStock for UI display before closing
      for (let opItem of opname.items) {
        const logs = await prisma.inventoryLog.aggregate({
          where: {
            itemId: opItem.inventoryItemId,
            type: 'IN',
            createdAt: { gte: opname.createdAt }
          },
          _sum: { quantity: true }
        });
        (opItem as any).addedStock = logs._sum.quantity || 0;
      }
      return res.json({ status: 'OPEN', opname });
    }

    const inventory = await prisma.inventoryItem.findMany();
    res.json({ status: 'NOT_OPEN', inventory });
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch opname status' });
  }
});

// POST /opname/open
router.post('/opname/open', async (req, res) => {
  try {
    const { items } = req.body;
    
    const existing = await prisma.dailyOpname.findFirst({ where: { status: 'OPEN' } });
    if (existing) return res.status(400).json({ error: 'Opname already open' });

    const opname = await prisma.dailyOpname.create({
      data: {
        status: 'OPEN',
        items: {
          create: items.map((i: any) => ({
            inventoryItemId: i.inventoryItemId,
            openingStock: i.openingStock,
            morningNotes: i.morningNotes,
          }))
        }
      },
      include: { items: true }
    });

    for (const i of items) {
      await prisma.inventoryItem.update({
        where: { id: i.inventoryItemId },
        data: { stock: i.openingStock }
      });
    }

    res.status(201).json(opname);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed to open opname' });
  }
});

// POST /opname/confirm-stock
router.post('/opname/confirm-stock', async (req, res) => {
  try {
    const opname = await prisma.dailyOpname.findFirst({
      where: { status: 'OPEN' }
    });
    if (!opname) {
      return res.status(400).json({ error: 'No open opname found' });
    }

    const updatedOpname = await prisma.dailyOpname.update({
      where: { id: opname.id },
      data: { isStockConfirmed: true }
    });

    res.json(updatedOpname);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed to confirm stock' });
  }
});

// POST /opname/cancel-confirm-stock
router.post('/opname/cancel-confirm-stock', async (req, res) => {
  try {
    const opname = await prisma.dailyOpname.findFirst({
      where: { status: 'OPEN' }
    });
    if (!opname) {
      return res.status(400).json({ error: 'No open opname found' });
    }

    const updatedOpname = await prisma.dailyOpname.update({
      where: { id: opname.id },
      data: { isStockConfirmed: false }
    });

    res.json(updatedOpname);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed to cancel confirm stock' });
  }
});

// POST /opname/close
router.post('/opname/close', async (req, res) => {
  try {
    const { opnameId, items } = req.body;
    
    const opname = await prisma.dailyOpname.findUnique({ where: { id: opnameId }, include: { items: true } });
    if (!opname || opname.status === 'CLOSED') {
      return res.status(400).json({ error: 'Invalid or already closed opname' });
    }

    for (const i of items) {
      const opItem = opname.items.find((oi: any) => oi.inventoryItemId === i.inventoryItemId);
      if (opItem) {
        // Find added stock during this opname period
        const logs = await prisma.inventoryLog.aggregate({
          where: {
            itemId: i.inventoryItemId,
            type: 'IN',
            createdAt: { gte: opname.createdAt }
          },
          _sum: { quantity: true }
        });
        const addedStock = logs._sum.quantity || 0;
        const used = (opItem.openingStock + addedStock) - i.closingStock;

        await prisma.dailyOpnameItem.update({
          where: { id: opItem.id },
          data: {
            closingStock: i.closingStock,
            addedStock: addedStock,
            used: used,
            nightNotes: i.nightNotes
          }
        });

        await prisma.inventoryItem.update({
          where: { id: i.inventoryItemId },
          data: { stock: i.closingStock }
        });
      }
    }

    const updatedOpname = await prisma.dailyOpname.update({
      where: { id: opnameId },
      data: { status: 'CLOSED' },
      include: { items: { include: { inventoryItem: true } } }
    });

    res.json(updatedOpname);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed to close opname' });
  }
});

// GET /opname/history
router.get('/opname/history', async (req, res) => {
  try {
    const history = await prisma.dailyOpname.findMany({
      where: { status: 'CLOSED' },
      include: { items: { include: { inventoryItem: true } } },
      orderBy: { createdAt: 'desc' }
    });
    res.json(history);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch opname history' });
  }
});

export default router;
