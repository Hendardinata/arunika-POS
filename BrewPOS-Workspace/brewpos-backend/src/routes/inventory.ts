import { Router } from 'express';
import { prisma } from '../db';

const router = Router();

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
router.post('/', async (req, res) => {
  try {
    const { name, stock, unit } = req.body;
    const item = await prisma.inventoryItem.create({
      data: { name, stock: parseInt(stock) || 0, unit: unit || 'pcs' },
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

export default router;
